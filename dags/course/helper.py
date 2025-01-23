import logging
from typing import List
import nest_asyncio
import llama_index.core
import os
from llama_index.core import Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_parse import LlamaParse
from dotenv import load_dotenv
from llama_index.core.schema import TextNode
import re
from pathlib import Path
from llama_index.core import (
    StorageContext,
    SummaryIndex,
    load_index_from_storage,
)
from llama_index.llms.openai import OpenAI
from utils.prompt_handler import PromptHandler
from pydantic import BaseModel, Field

"""
One function will be to parse and store the indexes.
One function will be to fetch the index.
One function will be to generate the outline.
One function will be to generate the slides.
"""

load_dotenv()
nest_asyncio.apply()

PHOENIX_API_KEY = os.getenv("PHOENIX_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_KEY")
LLAMAPARSE_API_KEY = os.getenv("LLAMAPARSE_API_KEY")
os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"api_key={PHOENIX_API_KEY}"

llama_index.core.set_global_handler(
    "arize_phoenix", endpoint="https://llamatrace.com/v1/traces"
)

embed_model = OpenAIEmbedding(model="text-embedding-3-large")
llm = OpenAI(model="gpt-4o")

Settings.embed_model = embed_model
Settings.llm = llm

parser = LlamaParse(
    result_type="markdown",
    use_vendor_multimodal_model=True,
    vendor_multimodal_model_name="anthropic-sonnet-3.5",
    api_key=LLAMAPARSE_API_KEY,
)

def get_page_number(file_name):
    match = re.search(r"-page-(\d+)\.jpg$", str(file_name))
    if match:
        return int(match.group(1))
    return 0

def _get_sorted_image_files(image_dir):
    # TODO change to s3 locations
    """Get image files sorted by page."""
    raw_files = [f for f in list(Path(image_dir).iterdir()) if f.is_file()]
    sorted_files = sorted(raw_files, key=get_page_number)
    return sorted_files

def get_text_nodes(json_dicts, image_dir=None):
    """Split docs into nodes, by separator."""
    nodes = []

    image_files = _get_sorted_image_files(image_dir) if image_dir is not None else None
    md_texts = [d["md"] for d in json_dicts]

    for idx, md_text in enumerate(md_texts):
        chunk_metadata = {"page_num": idx + 1}
        if image_files is not None:
            image_file = image_files[idx]
            chunk_metadata["image_path"] = str(image_file)
        chunk_metadata["parsed_text_markdown"] = md_text
        node = TextNode(
            text="",
            metadata=chunk_metadata,
        )
        nodes.append(node)

    return nodes

def parse_files(module_id, file_path, download_path):
    file_paths = [file_path for file_path in Path(file_path).iterdir()]
    md_json_objs = parser.get_json_result(file_path=file_paths)
    md_json_list = md_json_objs[0]["pages"]

    image_dir = download_path / index / "images"

    image_dicts = parser.get_images(md_json_objs, download_path=image_dir)

    text_nodes = get_text_nodes(md_json_list, image_dir=image_dir)

    index = SummaryIndex(text_nodes)
    index.set_index_id(module_id)
        
    return index

def save_index(index: SummaryIndex, path):
    index.storage_context.persist(persist_dir=path)
    
def load_index(module_id):
    """
    The index_id here is going to be the module id
    """
    path = Path("output") / module_id / "index"
    storage_context = StorageContext.from_defaults(persist_dir=path)
    index = load_index_from_storage(storage_context, index_id=module_id)
    return index



def _generate_outline(module_id, instructions):
    index = load_index(module_id)
    query_engine = index.as_query_engine(
        similarity_top_k=10,
        llm=llm,
        response_mode="compact",
    )

    prompt = PromptHandler().get_prompt("GET_OUTLINE_PROMPT")

    logging.info("Prompt for outline generation", prompt+instructions)

    response = query_engine.query(
        prompt+instructions
    )

    logging.info("Response for outline generation", response)

    return response.response

def generate_outline(artifacts_path, module_id, instructions):
    index = parse_files(module_id, artifacts_path, download_path=Path("output") / module_id)
    save_index(index, Path("output") / module_id / "index")
    outline = _generate_outline(module_id, instructions)
    return outline

def _break_outline(outline):
    pattern = r'(?m)^# .*$'
    matches = list(re.finditer(pattern, outline))
    
    # Initialize a list to hold the split sections
    sections = []

    # Iterate over the matches to extract sections
    for i in range(len(matches)):
        start = matches[i].start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(outline)
        sections.append(outline[start:end].strip())

    return sections

class TextBlock(BaseModel):
    """Text block for a slide."""

    text: str = Field(..., description="The text for this block. It should be in markdown format.")

class SpeakerNotes(BaseModel):
    """Speaker notes for a slide."""

    text: str = Field(..., description="The speaker notes for this slide.")

class SlideStructure(BaseModel):
    """Data model for a slide.
    
    Contains slide header, slide_content and the speaker notes for the slide.
    """

    slide_header: str = Field(..., description="The header for the slide.")
    slide_content: List[TextBlock] = Field(..., description="The content for the slide.")
    speaker_notes: SpeakerNotes = Field(..., description="The speaker notes for the slide.")



def get_slides(module_id, outline):
    index = load_index(module_id)
    sllm = llm.as_structured_llm(output_cls=SlideStructure)
    query_engine = index.as_query_engine(
        similarity_top_k=10,
        llm=sllm,
        response_mode="compact",
    )

    sections = _break_outline(outline)
    logging.info("Sections after breaking the outline", sections)

    prompt = PromptHandler().get_prompt("GET_SLIDE_PROMPT")

    slides = []

    for section in sections:
        response = query_engine.query(prompt + section)
        logging.info("Reponse for slide generation", response)
        slides.append({
            "slide_header": response.response.slide_header,
            "slide_content": response.response.slide_content,
            "speaker_notes": response.response.speaker_notes
        })

    return slides



        

def get_module_information(module_id):
    index = load_index(module_id)
    sllm = llm.as_structured_llm()
    query_engine = index.as_query_engine(
        similarity_top_k=10,
        llm=sllm,
        response_mode="compact",
    )

    prompt = PromptHandler().get_prompt("CONTENT_TO_SUMMARY_PROMPT")

    response = query_engine.query(prompt)

    logging.info("Prompt for module information generation", prompt)
    logging.info("Response for module information generation", response)

    return response.response