from pydantic import BaseModel, Field
from typing import List, Union
import logging
import re

class TextBlock(BaseModel):
    """Text block."""
    text: str = Field(..., description="The text for this block.")


class ImageBlock(BaseModel):
    """Image block."""
    file_path: str = Field(..., description="File path to the image.")


class OutlineOutput(BaseModel):
    """
    Data model for an outline.
    Can contain a mix of text and image blocks. in markdown format
    """
    blocks: List[Union[TextBlock, ImageBlock]] = Field(
        ..., description="A list of text and image blocks."
    )

    def render(self) -> str:
        rendered = []
        for block in self.blocks:
            if isinstance(block, TextBlock):
                rendered.append(block.text)
            elif isinstance(block, ImageBlock):
                rendered.append(f"![diagram]({block.file_path})")
        return "\n".join(rendered)


class SlideOutput(BaseModel):
    """Data model for a single slide."""
    slide_header: str = Field(..., description="The header for the slide.")
    slide_content: str = Field(..., description="The content for the slide.")
    speaker_notes: str = Field(..., description="The speaker notes for the slide.")


class MultiSlidesOutput(BaseModel):
    """
    Data model for multiple slides (to allow breaking one topic into multiple slides).
    Each slide is a SlideOutput.
    """
    slides: List[SlideOutput] = Field(..., description="List of slides.")


outline_system_prompt = prompt_handler.get_prompt("GET_OUTLINE_PROMPT")

outline_gen_llm = OpenAI(model=os.getenv("OPENAI_MODEL"), system_prompt=outline_system_prompt, api_key=OPENAI_KEY)
slide_gen_llm = OpenAI(
    model=os.getenv("OPENAI_MODEL"),
    system_prompt="system_prompt",
    api_key=OPENAI_KEY
)

outline_gen_sllm = llm.as_structured_llm(output_cls=OutlineOutput)
slide_gen_sllm = llm.as_structured_llm(output_cls=MultiSlidesOutput)


class InputEvent(Event):
    input: List[ChatMessage]


class ChunkRetrievalEvent(Event):
    tool_call: ToolSelection


class DocRetrievalEvent(Event):
    tool_call: ToolSelection


class OutputGenerationEvent(Event):
    pass


class SlidesGenerationAgent(Workflow):
    """Slides generation agent. Generates slides by first retrieving relevant chunks, etc."""

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

        user_input = ev.input
        user_msg = ChatMessage(role="user", content=user_input)
        self.memory.put(user_msg)
        chat_history = self.memory.get()
        return InputEvent(input=chat_history)

    @step(pass_context=True)
    async def handle_llm_input(
        self, ctx: Context, ev: InputEvent
    ) -> ChunkRetrievalEvent | DocRetrievalEvent | OutputGenerationEvent | StopEvent:
        logging.info("Handling LLM input")
        chat_history = ev.input

        response = await self.llm.achat_with_tools(
            [self.chunk_retriever_tool, self.doc_retriever_tool],
            chat_history=chat_history,
        )
        self.memory.put(response.message)

        tool_calls = self.llm.get_tool_calls_from_response(
            response, error_on_no_tool_call=False
        )
        if not tool_calls:
            # No tool calls; proceed to final output
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
        """Handle retrieval and store retrieved chunks."""
        query = ev.tool_call.tool_kwargs["query"]
        if isinstance(ev, ChunkRetrievalEvent):
            retrieved_chunks = self.chunk_retriever_tool(query).raw_output
        else:
            retrieved_chunks = self.doc_retriever_tool(query).raw_output

        ctx.data["stored_chunks"].extend(retrieved_chunks)

        # Summarize or "synthesize" as a single tool response
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

        # Next iteration with updated chat history
        return InputEvent(input=self.memory.get())

    @step(pass_context=True)
    async def generate_output(
        self, ctx: Context, ev: OutputGenerationEvent
    ) -> StopEvent:
        """Generate multi-slide output from context."""
        query = ctx.data["query"]
        stored_chunks = ctx.data["stored_chunks"]

        # Summarize / produce the final multi-slide output
        response = self.output_gen_summarizer.synthesize(query, nodes=stored_chunks)
        return StopEvent(result={"response": response})



logging.info("Loading index")
vector_index, summary_indexes = load_indexes(module_id)

logging.info("Creating tools")
chunk_retriever_tool = FunctionTool.from_defaults(
    fn=lambda query: chunk_retriever_fn(query, vector_index),
    name="chunk_retriever"
)
doc_retriever_tool = FunctionTool.from_defaults(
    fn=lambda query: doc_retriever_fn(query, vector_index, summary_indexes),
    name="doc_retriever"
)

# Create your slides agent with the new sllm = slide_gen_sllm (which returns MultiSlidesOutput)
agent = SlidesGenerationAgent(
    chunk_retriever_tool=chunk_retriever_tool,
    doc_retriever_tool=doc_retriever_tool,
    llm=slide_gen_llm,
    sllm=slide_gen_sllm,
    verbose=True,
    timeout=360.0,
)

outline = "...whatever your user provided..."
sections = _break_outline(outline)  # You have this function somewhere
logging.info("Sections after breaking the outline: "+str(len(sections)))

slides = []

for section in sections:
    logging.info("Section: " + section)

    # Use last few slides (if you want context continuity)
    previous_slides = slides[-3:] if len(slides) > 3 else slides

    # Prompt instructs the agent to create multiple slides if it sees fit
    # For example:
    prompt_for_section = (
        "Help me generate 1 or more slides (up to 3) for the following topic, "
        "after retrieving relevant information. If you have a mermaid diagram or image, "
        "put it on its own slide with no other text. Each bullet or diagram must have 3-5 lines "
        "in the speaker notes. Do not include opening comments like 'In this slide...' in the notes. "
        "Maintain flow from previous slides. Return JSON with the format:\n\n"
        "{\n"
        "  \"slides\": [\n"
        "    {\n"
        "      \"slide_header\": \"...\",\n"
        "      \"slide_content\": \"...\",\n"
        "      \"speaker_notes\": \"...\"\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Previously generated slides:\n"
        f"{previous_slides}\n\n"
        "Next topic:\n"
        f"{section}"
    )

    # Run the agent
    response = await agent.run(input=prompt_for_section)
    logging.info("Response from slides agent: ")
    logging.info(response)

    # The agent returns a MultiSlidesOutput. Access them:
    multi_slides_output = response["response"].response  # This is MultiSlidesOutput
    for single_slide in multi_slides_output.slides:
        # Optionally clean up or do additional processing:
        # E.g. convert local images or do something with mermaid code blocks
        sc = re.sub(r'\n+', '\n', single_slide.slide_content)
        slides.append({
            "slide_header": single_slide.slide_header,
            "slide_content": sc,
            "speaker_notes": single_slide.speaker_notes
        })

# Insert the welcome and final "thank you" slides
llm = LLM()
prompt = PromptHandler().get_prompt("GET_WELCOME_THANK_YOU_SLIDE_PROMPT")
prompt = PromptTemplate(template=prompt, inputs=["SLIDES", "MODULE_NAME"])

response = llm.get_response(
    prompt,
    inputs={"SLIDES": str(slides), "MODULE_NAME": module_name}
)

try:
    # example for your JSON parse
    parsed = json.loads(response[response.index("{"):response.rindex("}")+1])
    welcome_message = parsed["welcome_slide"]["speaker_notes"]
    thank_you_message = parsed["thank_you_slide"]["speaker_notes"]
except:
    welcome_message = f"Hello, welcome to the module: {module_name}"
    thank_you_message = "Thank you for completing the module."

slides.insert(
    0,
    {
        "slide_header": "",
        "slide_content": f"# {module_name}",
        "speaker_notes": welcome_message
    }
)
slides.append(
    {
        "slide_header": "",
        "slide_content": "![](https://qucoursify.s3.us-east-1.amazonaws.com/qu-skillbridge/last_page.png)",
        "speaker_notes": thank_you_message
    }
)

# At this point, 'slides' is your final array, each element can be a dictionary
# with "slide_header", "slide_content", "speaker_notes".
# This approach allows the LLM to produce multiple slides per outline section,
# includes mermaid code blocks if it wants, and ensures each bullet/diagram
# is on its own slide with enough speaker notes.
