from utils.llm import LLM
import json
import asyncio
from typing import Any, List
from llama_index.core.llms.function_calling import FunctionCallingLLM
from llama_index.core.llms.structured_llm import StructuredLLM
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.llms import ChatMessage
from llama_index.core.tools.types import BaseTool
from llama_index.core.tools import ToolSelection
from llama_index.core.workflow import Workflow, StartEvent, StopEvent, Context, step
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import CompactAndRefine
from llama_index.core.workflow import Event
from operator import itemgetter
from llama_index.core.tools import FunctionTool
from llama_index.core.schema import NodeWithScore
import pickle
import logging
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
    VectorStoreIndex,
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

embed_model = OpenAIEmbedding(
    model="text-embedding-3-large", api_key=OPENAI_KEY)
llm = OpenAI(model=os.getenv("OPENAI_MODEL"), api_key=OPENAI_KEY)

Settings.embed_model = embed_model
Settings.llm = llm

parser = LlamaParse(
    result_type="markdown",
    use_vendor_multimodal_model=True,
    vendor_multimodal_model_name="openai-gpt-4o-mini",
    vendor_multimodal_api_key=OPENAI_KEY,
    api_key=LLAMAPARSE_API_KEY,
    fast_mode=True,
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


def get_text_nodes(json_dicts, file_path):
    """Split docs into nodes, by separator."""
    nodes = []
    md_texts = []
    for d in json_dicts:
        if "md" in d:
            md_texts.append(d["md"])
        else:
            text = d["text"]
            # Replace multiple spaces/tabs with a single space
            cleaned_text = re.sub(r'[ \t]+', ' ', text)
            # Remove extra blank lines
            cleaned_text = re.sub(r'\n\s*\n', '\n', cleaned_text)
            md_texts.append(cleaned_text)
        chunk_metadata = {
            "page_num": d["page"],
            "parsed_text_markdown": md_texts[-1],
            "file_path": str(file_path),

        }
        if "images" in d:
            image_paths = [img['path'] for img in d["images"]]
            chunk_metadata["image_paths"] = image_paths

        node = TextNode(
            text="",
            metadata=chunk_metadata,
        )

        nodes.append(node)

    return nodes


def parse_files(module_id, file_path, download_path):
    file_paths = [file_path for file_path in Path(
        file_path).iterdir() if file_path.suffix == ".pdf"]

    file_dicts = {}

    for file_path in file_paths:
        file_base = Path(file_path).stem
        full_file_path = file_path
        md_json_objs = parser.get_json_result(file_path)
        print(md_json_objs)
        json_dicts = md_json_objs[0]["pages"]

        image_path = str(Path(download_path) / file_base)
        image_dicts = parser.get_images(md_json_objs, download_path=image_path)
        file_dicts[file_path] = {
            "file_path": full_file_path,
            "json_dicts": json_dicts,
            "image_path": image_path,
        }

    all_text_nodes = []
    text_nodes_dict = {}
    for file_path, file_dict in file_dicts.items():
        json_dicts = file_dict["json_dicts"]
        text_nodes = get_text_nodes(json_dicts, file_dict["file_path"])
        all_text_nodes.extend(text_nodes)
        text_nodes_dict[file_path] = text_nodes

    output_pickle_path = Path("output") / module_id / "text_nodes_pickle.pkl"
    pickle.dump(text_nodes_dict, open(output_pickle_path, "wb"))

    logging.info("All text nodes:")
    logging.info(all_text_nodes)

    vector_index = VectorStoreIndex(all_text_nodes)
    vector_index.set_index_id(f"{module_id}_vector_index")

    return vector_index


def save_index(vector_index: VectorStoreIndex, vector_index_path):
    vector_index.storage_context.persist(persist_dir=vector_index_path)


def load_indexes(module_id):
    """
    The index_id here is going to be the module id
    """

    text_nodes_dict = pickle.load(
        open(Path("output") / module_id / "text_nodes_pickle.pkl", "rb"))

    all_text_nodes = []
    for file_path, text_nodes in text_nodes_dict.items():
        all_text_nodes.extend(text_nodes)

    summary_indexes = {
        file_path: SummaryIndex(text_nodes_dict[file_path]) for file_path, text_nodes in text_nodes_dict.items()
    }

    path = Path("output") / module_id / "vector_index"
    storage_context = StorageContext.from_defaults(persist_dir=path)
    vector_index = load_index_from_storage(
        storage_context, index_id=f"{module_id}_vector_index")

    return vector_index, summary_indexes


# function tools
def chunk_retriever_fn(query: str, vector_index) -> List[NodeWithScore]:
    """Retrieves a small set of relevant document chunks from the corpus.

    ONLY use for research questions that want to look up specific facts from the knowledge corpus,
    and don't need entire documents.

    """
    retriever = vector_index.as_retriever(similarity_top_k=5)
    nodes = retriever.retrieve(query)
    return nodes


def _get_document_nodes(
    nodes: List[NodeWithScore],
    summary_indexes: dict,
    top_n: int = 5
) -> List[NodeWithScore]:
    """Get document nodes from a set of chunk nodes.

    Given chunk nodes, "de-reference" into a set of documents, with a simple weighting function (cumulative total) to determine ordering.

    Cutoff by top_n.

    """
    file_paths = {n.metadata["file_path"] for n in nodes}
    file_path_scores = {f: 0 for f in file_paths}
    for n in nodes:
        file_path_scores[n.metadata["file_path"]] += n.score

    # Sort file_path_scores by score in descending order
    sorted_file_paths = sorted(
        file_path_scores.items(), key=itemgetter(1), reverse=True
    )
    # Take top_n file paths
    top_file_paths = [path for path, score in sorted_file_paths[:top_n]]

    # use summary index to get nodes from all file paths
    all_nodes = []
    for file_path in top_file_paths:
        # NOTE: input to retriever can be blank
        all_nodes.extend(
            summary_indexes[Path(file_path)].as_retriever().retrieve("")
        )

    return all_nodes


def doc_retriever_fn(query: str, index, summary_indexes) -> float:
    """Document retriever that retrieves entire documents from the corpus.

    ONLY use for research questions that may require searching over entire research reports.

    Will be slower and more expensive than chunk-level retrieval but may be necessary.
    """
    retriever = index.as_retriever(similarity_top_k=5)
    nodes = retriever.retrieve(query)
    return _get_document_nodes(nodes, summary_indexes)


class TextBlock(BaseModel):
    """Text block."""

    text: str = Field(..., description="The text for this block.")


class ImageBlock(BaseModel):
    """Image block."""

    file_path: str = Field(..., description="File path to the image.")


class OutlineOutput(BaseModel):
    """Data model for a outline.

    Can contain a mix of text and image blocks. in markdown format

    """

    blocks: List[TextBlock | ImageBlock] = Field(
        ..., description="A list of text and image blocks."
    )


class SlideOutput(BaseModel):
    """Data model for a slide.

    Contains slide header, slide_content and the speaker notes for the slide.

    """

    slide_header: str = Field(..., description="The header for the slide.")
    slide_content: str = Field(..., description="The content for the slide.")
    speaker_notes: str = Field(...,
                               description="The speaker notes for the slide.")


class ModuleInformationOutput(BaseModel):
    """Data model for module information.

    Contains the module information.

    """

    module_information: str = Field(
        ..., description="The module information summarized in 2 lines and 3-5 bullet points in markdown format.")


prompt_handler = PromptHandler()
outline_system_prompt = prompt_handler.get_prompt("GET_OUTLINE_PROMPT")
slide_system_prompt = prompt_handler.get_prompt("GET_SLIDE_PROMPT")
module_information_system_prompt = prompt_handler.get_prompt(
    "CONTENT_TO_SUMMARY_PROMPT")

outline_gen_llm = OpenAI(model=os.getenv(
    "OPENAI_MODEL"), system_prompt=outline_system_prompt, api_key=OPENAI_KEY)
slide_gen_llm = OpenAI(model=os.getenv("OPENAI_MODEL"),
                       system_prompt=slide_system_prompt, api_key=OPENAI_KEY)
module_information_gen_llm = OpenAI(model=os.getenv(
    "OPENAI_MODEL"), system_prompt=module_information_system_prompt, api_key=OPENAI_KEY)

outline_gen_sllm = llm.as_structured_llm(output_cls=OutlineOutput)
slide_gen_sllm = llm.as_structured_llm(output_cls=SlideOutput)
module_information_gen_sllm = llm.as_structured_llm(
    output_cls=ModuleInformationOutput)


class InputEvent(Event):
    input: List[ChatMessage]


class ChunkRetrievalEvent(Event):
    tool_call: ToolSelection


class DocRetrievalEvent(Event):
    tool_call: ToolSelection


class OutputGenerationEvent(Event):
    pass


class SlidesGenerationAgent(Workflow):
    """Slides generation agent. Generates the slides based on the input by first retrieving relevant chunks and documents from the corpus."""

    def __init__(
        self,
        chunk_retriever_tool: BaseTool,
        doc_retriever_tool: BaseTool,
        llm: FunctionCallingLLM | None = None,
        sllm: StructuredLLM | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.chunk_retriever_tool = chunk_retriever_tool
        self.doc_retriever_tool = doc_retriever_tool

        self.llm = llm
        self.summarizer = CompactAndRefine(llm=self.llm)
        assert self.llm.metadata.is_function_calling_model

        self.sllm = sllm
        self.output_gen_summarizer = CompactAndRefine(llm=self.sllm)

        self.memory = ChatMemoryBuffer.from_defaults(llm=llm)
        self.sources = []

    @step(pass_context=True)
    async def prepare_chat_history(self, ctx: Context, ev: StartEvent) -> InputEvent:
        # clear sources
        self.sources = []

        ctx.data["stored_chunks"] = []
        ctx.data["query"] = ev.input

        # get user input
        user_input = ev.input
        user_msg = ChatMessage(role="user", content=user_input)
        self.memory.put(user_msg)

        # get chat history
        chat_history = self.memory.get()
        return InputEvent(input=chat_history)

    @step(pass_context=True)
    async def handle_llm_input(
        self, ctx: Context, ev: InputEvent
    ) -> ChunkRetrievalEvent | DocRetrievalEvent | OutputGenerationEvent | StopEvent:
        logging.info("Handling LLM input")
        chat_history = ev.input

        logging.info("Chat history: "+str(chat_history))

        response = await self.llm.achat_with_tools(
            [self.chunk_retriever_tool, self.doc_retriever_tool],
            chat_history=chat_history,
        )
        print("Response from async chat with tools function: ", response)
        self.memory.put(response.message)
        print("Memory: ", self.memory.get())

        tool_calls = self.llm.get_tool_calls_from_response(
            response, error_on_no_tool_call=False
        )
        print("Tool calls: ", tool_calls)
        if not tool_calls:
            # all the content should be stored in the context, so just pass along input
            return OutputGenerationEvent(input=ev.input)

        for tool_call in tool_calls:
            if tool_call.tool_name == self.chunk_retriever_tool.metadata.name:
                return ChunkRetrievalEvent(tool_call=tool_call)
            elif tool_call.tool_name == self.doc_retriever_tool.metadata.name:
                return DocRetrievalEvent(tool_call=tool_call)
            else:
                return StopEvent(result={"response": "Invalid tool."})

    @step(pass_context=True)
    async def handle_retrieval(
        self, ctx: Context, ev: ChunkRetrievalEvent | DocRetrievalEvent
    ) -> InputEvent:
        """Handle retrieval.

        Store retrieved chunks, and go back to agent reasoning loop.
        """
        logging.info("Handling retrieval")
        query = ev.tool_call.tool_kwargs["query"]
        if isinstance(ev, ChunkRetrievalEvent):
            logging.info("Retrieving chunks")
            retrieved_chunks = self.chunk_retriever_tool(query).raw_output
        else:
            logging.info("Retrieving docs")
            retrieved_chunks = self.doc_retriever_tool(query).raw_output
        ctx.data["stored_chunks"].extend(retrieved_chunks)

        # synthesize an answer given the query to return to the LLM.
        response = self.summarizer.synthesize(query, nodes=retrieved_chunks)
        self.memory.put(
            ChatMessage(
                role="tool",
                content=str(response),
                additional_kwargs={
                    "tool_call_id": ev.tool_call.tool_id,
                    "name": ev.tool_call.tool_name,
                },
            )
        )

        # send input event back with updated chat history
        return InputEvent(input=self.memory.get())

    @step(pass_context=True)
    async def generate_output(
        self, ctx: Context, ev: OutputGenerationEvent
    ) -> StopEvent:
        """Generate the final slide based on the context of the inputs from the retrieval tools."""
        # given all the context, generate query
        print("Calling the output generation final event")
        print(ctx.data["query"])
        print(ctx.data["stored_chunks"])
        response = self.output_gen_summarizer.synthesize(
            ctx.data["query"], nodes=ctx.data["stored_chunks"]
        )
        print("Response from output generation: ", response)

        return StopEvent(result={"response": response})


async def generate_outline(module_id, instructions):
    logging.info("Loading index")
    vector_index, summary_indexes = load_indexes(module_id)
    logging.info("Index loaded")

    query_engine = vector_index.as_query_engine(
        similarity_top_k=5,
        llm=outline_gen_llm,
    )
    logging.info("Instructions for outline generation:\n"+instructions)
    response = query_engine.query(instructions)
    response = response.response
    response = response.replace("```markdown", "").replace(
        "```", "").replace("```", "").replace("markdown", "")
    logging.info("Response for agent's output: "+response)

    return response


def _break_outline(outline):

    # ask chatgpt to break the outline into slides
    # return the output as a list
    prompt = PromptHandler().get_prompt("BREAK_OUTLINE_PROMPT")
    llm = LLM()
    response = llm.get_response(prompt+outline)
    print(response[response.find("["):response.rfind("]")+1])
    response = json.loads(response[response.find("["):response.rfind("]")+1])
    return response


async def get_slides(module_id, outline):
    logging.info("Loading index")
    vector_index, summary_indexes = load_indexes(module_id)

    logging.info("Creating tools")
    chunk_retriever_tool = FunctionTool.from_defaults(
        fn=lambda query: chunk_retriever_fn(query, vector_index), name="chunk_retriever")
    doc_retriever_tool = FunctionTool.from_defaults(fn=lambda query: doc_retriever_fn(
        query, vector_index, summary_indexes), name="doc_retriever")

    agent = SlidesGenerationAgent(
        chunk_retriever_tool=chunk_retriever_tool,
        doc_retriever_tool=doc_retriever_tool,
        llm=slide_gen_llm,
        sllm=slide_gen_sllm,
        verbose=True,
        timeout=360.0,
    )

    sections = _break_outline(outline)
    logging.info("Sections after breaking the outline: "+str(len(sections)))

    slides = []

    for section in sections:
        logging.info("Section: "+section)
        response = await agent.run(input="Help me get the slide header, slide content and the speaker notes for ONE SLIDE for the following topic after retrieving relevant information to the following topic from the tools. The slide header should be short and descriptive. The slide content should be descriptive and have 3-5 bullet points. The speaker notes should be as if presenting the topic on teh slides based on the slide content and should be in a continuous flow.\n"+section)

        slides.append({
            "slide_header": response['response'].response.slide_header,
            "slide_content": response['response'].response.slide_content,
            "speaker_notes": response['response'].response.speaker_notes
        })

    return slides


async def get_module_information(module_id, outline):

    # generate teh module information using an llm
    prompt = PromptHandler().get_prompt("GET_MODULE_INFORMATION_PROMPT")
    llm = LLM()
    response = llm.get_response(
        prompt+str(outline).replace("{", "{{").replace("}", "}}"))
    print(response)

    return response
