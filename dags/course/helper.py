# Standard library imports 
import asyncio
import json
import logging
import os
import re
import subprocess
import pickle
import re
import time
from operator import itemgetter
from pathlib import Path
from typing import Any, List

# Third-party imports
from dotenv import load_dotenv
import nest_asyncio
from llama_parse import LlamaParse
from pydantic import BaseModel, Field

# Llama index imports
from langchain.prompts.prompt import PromptTemplate
import llama_index.core
from llama_index.core import Settings, StorageContext, SummaryIndex, VectorStoreIndex, load_index_from_storage
from llama_index.core.llms.function_calling import FunctionCallingLLM
from llama_index.core.llms.structured_llm import StructuredLLM
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.llms import ChatMessage
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import CompactAndRefine
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.core.tools import BaseTool, FunctionTool, ToolSelection
from llama_index.core.workflow import Context, Event, StartEvent, StopEvent, Workflow, step
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI

# Local imports
from utils.llm import LLM
from utils.mongodb_client import AtlasClient
from utils.prompt_handler import PromptHandler
from utils.s3_file_manager import S3FileManager


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

    s3 = S3FileManager()

    for file_path in file_paths:
        file_base = Path(file_path).stem
        full_file_path = file_path
        md_json_objs = []
        while not md_json_objs:
            md_json_objs = parser.get_json_result(file_path)
            time.sleep(5)

        logging.info(md_json_objs)
        json_dicts = md_json_objs[0]["pages"]

        image_path_ = str(Path(download_path) / file_base)
        image_dicts = parser.get_images(md_json_objs, download_path=image_path_)
        logging.info(image_dicts)

        # store all the images in s3
        for index, image_dict in enumerate(image_dicts):
            image_path = image_dict["path"]
            key = f"qu-course-design/{image_path[image_path.index('output/')+7:]}"
            asyncio.run(s3.upload_png_image(image_path, key))
            link = "https://qucoursify.s3.us-east-1.amazonaws.com/"+key
            image_dicts[index]["path"] = link

        file_dicts[file_path] = {
            "file_path": full_file_path,
            "json_dicts": json_dicts,
            "image_path": image_path_,
        }

    all_text_nodes = []
    text_nodes_dict = {}
    for file_path, file_dict in file_dicts.items():
        json_dicts = file_dict["json_dicts"]
        text_nodes = get_text_nodes(json_dicts, file_dict["file_path"])
        all_text_nodes.extend(text_nodes)
        text_nodes_dict[file_path] = text_nodes
        
    logging.info("All text nodes\n")
    logging.info(all_text_nodes)
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

    def render(self) -> str:
        """Render the blocks as a string."""
        rendered = []
        for block in self.blocks:
            if isinstance(block, TextBlock):
                rendered.append(block.text)
            elif isinstance(block, ImageBlock):
                rendered.append(f"![diagram]({block.file_path})")
        return "\n".join(rendered)


class SlideOutput(BaseModel):
    """Data model for a slide.

    Contains slide header, slide_content and the speaker notes for the slide.
    """

    slide_header: str = Field(..., description="The header for the slide.")
    slide_content: str = Field(..., description="The content for the slide.")
    speaker_notes: str = Field(...,
                               description="The speaker notes for the slide.")


class MultiSlidesOutput(BaseModel):
    """
    Data model for multiple slides (to allow breaking one topic into multiple slides).
    Each slide is a SlideOutput.
    """
    slides: List[SlideOutput] = Field(..., description="List of slides.")

class ModuleInformationOutput(BaseModel):
    """Data model for module information.

    Contains the module information.

    """

    module_information: str = Field(
        ..., description="The module information summarized in 2 lines and 3-5 bullet points in markdown format.")


prompt_handler = PromptHandler()
outline_system_prompt = prompt_handler.get_prompt("GET_OUTLINE_PROMPT")
slide_system_prompt = prompt_handler.get_prompt("GET_SLIDE_PROMPT")
module_information_system_prompt = prompt_handler.get_prompt("CONTENT_TO_SUMMARY_PROMPT")

outline_gen_llm = OpenAI(model=os.getenv("OPENAI_MODEL"), system_prompt=outline_system_prompt, api_key=OPENAI_KEY)
slide_gen_llm = OpenAI(model=os.getenv("OPENAI_MODEL"),
                       system_prompt=slide_system_prompt, api_key=OPENAI_KEY)
module_information_gen_llm = OpenAI(model=os.getenv("OPENAI_MODEL"), system_prompt=module_information_system_prompt, api_key=OPENAI_KEY)

outline_gen_sllm = llm.as_structured_llm(output_cls=OutlineOutput)
slide_gen_sllm = llm.as_structured_llm(output_cls=MultiSlidesOutput)
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


class OutlineGenerationAgent(Workflow):
    """Outline generation agent. Generates the outline based on the input by first retrieving relevant chunks and documents from the corpus."""

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
        logging.info("Response from async chat with tools function: ")
        logging.info(response)
        self.memory.put(response.message)
        logging.info("Memory: ")
        logging.info(self.memory.get())

        tool_calls = self.llm.get_tool_calls_from_response(
            response, error_on_no_tool_call=False
        )
        logging.info("Tool calls: ")
        logging.info(tool_calls)
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
        """Generate the outline based on the context of the inputs from the retrieval tools."""
        # given all the context, generate query
        logging.info("Calling the output generation final event")
        logging.info(ctx.data["query"])
        logging.info(ctx.data["stored_chunks"])
        response = self.output_gen_summarizer.synthesize(
            ctx.data["query"], nodes=ctx.data["stored_chunks"]
        )
        logging.info("Response from output generation: ")
        logging.info(response)

        return StopEvent(result={"response": response})


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
        logging.info("Response from async chat with tools function: ")
        logging.info(response)
        self.memory.put(response.message)
        logging.info("Memory: ")
        logging.info(self.memory.get())

        tool_calls = self.llm.get_tool_calls_from_response(
            response, error_on_no_tool_call=False
        )
        logging.info("Tool calls: ")
        logging.info(tool_calls)
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
        logging.info("Calling the output generation final event")
        logging.info(ctx.data["query"])
        logging.info(ctx.data["stored_chunks"])
        response = self.output_gen_summarizer.synthesize(
            ctx.data["query"], nodes=ctx.data["stored_chunks"]
        )
        logging.info("Response from output generation: ")
        logging.info(response)

        return StopEvent(result={"response": response})


async def generate_outline(module_id, instructions):
    logging.info("Loading index")
    vector_index, summary_indexes = load_indexes(module_id)
    logging.info("Index loaded")

    logging.info("Creating tools")
    # chunk_retriever_tool = FunctionTool.from_defaults(
    #     fn=lambda query: chunk_retriever_fn(query, vector_index), name="chunk_retriever")
    # doc_retriever_tool = FunctionTool.from_defaults(fn=lambda query: doc_retriever_fn(
    #     query, vector_index, summary_indexes), name="doc_retriever")

    from smolagents import CodeAgent, LiteLLMModel, tool, DuckDuckGoSearchTool
    
    @tool
    def chunk_retriever_tool_for_codeagent(query: str) -> List[NodeWithScore]:
        """Retrieves a small set of relevant document chunks from the corpus.

        ONLY use for research questions that want to look up specific facts from the knowledge corpus,
        and don't need entire documents.
        
        Args:
            query (str): The query to retrieve the chunks for.
        Returns:
            List[NodeWithScore]: The list of retrieved chunks.
        """
        retriever = vector_index.as_retriever(similarity_top_k=5)
        nodes = retriever.retrieve(query)
        return nodes      
    
    @tool
    def doc_retriever_tool_for_codeagent(query: str) -> List[NodeWithScore]:
        """Document retriever that retrieves entire documents from the corpus.

        ONLY use for research questions that may require searching over entire research reports.

        Will be slower and more expensive than chunk-level retrieval but may be necessary.
        
        Args:
            query (str): The query to retrieve the documents for.
        Returns:
            List[NodeWithScore]: The list of retrieved documents.
        """
        retriever = vector_index.as_retriever(similarity_top_k=5)
        nodes = retriever.retrieve(query)
        return _get_document_nodes(nodes, summary_indexes)
    
    tools = [
        chunk_retriever_tool_for_codeagent,
        doc_retriever_tool_for_codeagent,
        DuckDuckGoSearchTool()
    ]
    
    model = LiteLLMModel(model_id=os.getenv("AGENT_MODEL"), api_key=os.getenv("AGENT_KEY"))
    agent = CodeAgent(model=model, tools=tools)
    
    response = agent.run(
        "Help me get the outline for the following topic after retrieving relevant information to the following topic from the tools. If the document contains an index with the topic and subtopics listed, prioritize using it. Also compulsorily have some slides with mermaid diagrams and images in the outline depending on the content. There should be at least one mermaid diagram or at least one image. The outline should be in markdown format.\n"+instructions
    )
    
    logging.info("Outline generated: ")
    logging.info(response)
    
    outline = response  
    outline = convert_mermaid_diagrams_to_links(outline, module_id)
    logging.info("Outline generated: ")
    
    # agent = OutlineGenerationAgent(
    #     chunk_retriever_tool=chunk_retriever_tool,
    #     doc_retriever_tool=doc_retriever_tool,
    #     llm=outline_gen_llm,
    #     sllm=outline_gen_sllm,
    #     verbose=True,
    #     timeout=360.0,
    # )

    # outline = await agent.run(
    #     input="Help me get the outline for the following topic after retrieving relevant information to the following topic from the tools. If the document contains an index with the topic and subtopics listed, prioritize using it. Also compulsorily have some slides with mermaid diagrams and images in the outline depending on the content. There should be at least one mermaid diagram or at least one image. The outline should be in markdown format.\n"+instructions)
    # logging.info("Outline generated: ")
    # logging.info(outline)
    
    # outline = outline['response'].response.render()
    outline = outline.replace("```markdown", "").replace("```", "").replace("```", "").replace("markdown", "")
    logging.info("Outline generated: ")
    logging.info(outline)

    return outline


def convert_mermaid_diagrams_to_links(markdown, module_id):
    """
    Convert Mermaid code blocks in Markdown to PNGs and replace them with image links.
    """
    logging.info("Converting Mermaid code blocks to PNGs")
    import uuid
    unique_id = str(uuid.uuid4())
    markdown_file_name = f"output/{module_id}/{unique_id}.md"
    markdown_file = open(markdown_file_name, "w")
    markdown =  re.sub(r'\n{3,}', '\n\n', markdown).strip()
    markdown_file.write(markdown.replace("<br />", "\n"))
    markdown_file.close()
    markdown_file_abs_path = os.path.abspath(markdown_file_name)
    logging.info(f"Running command: npx -p @mermaid-js/mermaid-cli -p puppeteer mmdc -i {markdown_file_abs_path} -o {markdown_file_abs_path} --outputFormat=png")
    command = f"npx --yes -p @mermaid-js/mermaid-cli -p puppeteer mmdc -i {markdown_file_abs_path} -o {markdown_file_abs_path} --outputFormat=png --scale 5"

    response = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
    logging.info("Response from command: "+str(response))

    # push all the generated image files in the file_path to s3, and replace the files to s3 links
    markdown_file = open(markdown_file_name, "r")
    markdown_content = markdown_file.readlines()
    markdown_file.close()

    logging.info("Original File")
    logging.info(markdown_content)

    s3 = S3FileManager()

    rewritten_markdown_content = []
    to_be_deleted_files = []
    # if line startswith ![diagram](./output-svg, replace it with ![diagram](s3 link)
    for line in markdown_content:
        if line.startswith("![diagram]"):
            file_name = line.split("(")[1].split(")")[0][2:]
            file_path = f"output/{module_id}/" + file_name
            logging.info("File path (mermaid): "+file_path)
            key = "qucoursify/qu-course-design/"+module_id+"/slides/"+file_path
            asyncio.run(s3.upload_png_image(file_path, key))
            link = "https://qucoursify.s3.us-east-1.amazonaws.com/"+key
            logging.info("Link: "+link)
            rewritten_markdown_content.append(f"![]({link})")
        else:
            rewritten_markdown_content.append(line.strip())
    

    return "\n".join(rewritten_markdown_content)


def _break_outline(outline):

    # ask chatgpt to break the outline into slides
    # return the output as a list
    prompt = PromptHandler().get_prompt("BREAK_OUTLINE_PROMPT")
    llm = LLM()
    
    response = llm.get_response(PromptTemplate(template=prompt, inputs=["OUTLINE"]), inputs={"OUTLINE": outline})
    logging.info(response[response.find("["):response.rfind("]")+1])
    response = json.loads(response[response.find("["):response.rfind("]")+1])
    return response


async def get_slides(module_id, outline, module_name):
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
        previous_slides = slides[-3:] if len(slides) > 3 else slides
        prompt_for_section = slide_system_prompt.replace("{PREVIOUS_SLIDES}", str(previous_slides)).replace("{NEXT_TOPIC}", section)
        response = await agent.run(input=prompt_for_section)
        logging.info("Response from async chat with tools function: ")
        logging.info(response)
        multi_slides_output = response["response"].response
        for single_slide in multi_slides_output.slides:
            sc = re.sub(r'\n+', '\n', single_slide.slide_content)
            sc = convert_mermaid_diagrams_to_links(sc, module_id)
            if "$$$start-markdown" in sc:
                sc = sc[sc.index("$$$start-markdown")+12:sc.rindex("$$$end-markdown")]
            slides.append({
                "slide_header": single_slide.slide_header,
                "slide_content": sc,
                "speaker_notes": single_slide.speaker_notes
            })
        

    # get the first welcome slide and the last thank you slide for the module.
    llm = LLM()
    prompt = PromptHandler().get_prompt("GET_WELCOME_THANK_YOU_SLIDE_PROMPT")
    prompt = PromptTemplate(template=prompt, inputs=["SLIDES", "MODULE_NAME"])
    response = llm.get_response(prompt, inputs={"SLIDES": str(slides), "MODULE_NAME": module_name})
    welcome_message = ""
    thank_you_message = ""

    try:
        response = json.loads(response[response.index("```json")+7:response.rindex("```")])
        welcome_message = response["welcome_slide"]["speaker_notes"]
        thank_you_message = response["thank_you_slide"]["speaker_notes"]
    except:
        try:
            response = json.loads(response[response.index("{"):response.rindex("}")+1])
            welcome_message = response["welcome_slide"]["speaker_notes"]
            thank_you_message = response["thank_you_slide"]["speaker_notes"]
        except:
            logging.info("Error in parsing the welcome and thank you message")
            welcome_message = "Hello, welcome to the module: "+module_name
            thank_you_message = "Thank you for completing the module."

    slides.insert(0, {
        "slide_header": "",
        "slide_content": f"% {module_name}",
        "speaker_notes": welcome_message
    })
    slides.append({
        "slide_header": "",
        "slide_content": "![](https://qucoursify.s3.us-east-1.amazonaws.com/qu-skillbridge/last_page.png)",
        "speaker_notes": thank_you_message
    })
    
    # get structured response for the slide if it is not in the proper structure
    # if isinstance(slides, str):
    #     try:
    #         slides = json.loads(slides[slides.index("["):slides.rindex("]")+1])
    #         # check if structure is correct
    #         if not isinstance(slides, list):
    #             raise Exception("Not a list")
    #         for slide in slides:
    #             if not isinstance(slide, dict):
    #                 raise Exception("Not a dict")
    #             if "slide_header" not in slide or "slide_content" not in slide or "speaker_notes" not in slide:
    #                 raise Exception("Not in proper format")
    #     except:
    #         message="""
    #         Given the slides, generate it in proper format according to the following format:
    #         ```json
    #         [
    #             {
    #                 "slide_header": "Slide Header",
    #                 "slide_content": "Slide content in Markdown",
    #                 "speaker_notes": "Corresponding speaker notes"
    #             },
    #             {
    #                 "slide_header": "Next Slide Header",
    #                 "slide_content": "Next slide content in Markdown",
    #                 "speaker_notes": "Corresponding speaker notes"
    #             }
    #             ...
    #         ]
    #         ```
    #         """
            
    #         from litellm import completion
    #         slides = completion(model=os.getenv("OPENAI_MODEL"),  api_key=os.getenv("OPENAI_KEY"),
    #                             messages=[
    #                                 {"role": "user", "content": message},
    #                                 {"role": "user", "content": "The slides are: "+str(slides)},
    #                             ]
    #             )
    #         logging.info("Response from the LLM: "+str(slides))
    #         slides = json.loads(slides[slides.index("["):slides.rindex("]")+1])
    #         logging.info("Slides after parsing: "+str(slides))

    return slides


async def get_module_information(module_id, outline):

    # generate teh module information using an llm
    logging.info("Creating information for the outline")
    logging.info(outline)
    prompt = PromptHandler().get_prompt("GET_MODULE_INFORMATION_PROMPT")
    prompt = PromptTemplate(template=prompt, inputs=["OUTLINE"])
    llm = LLM()
    response = llm.get_response(prompt, inputs={"OUTLINE": outline})
    logging.info(response)

    return response
