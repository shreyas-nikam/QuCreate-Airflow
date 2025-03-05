# Langchain imports
from langchain_openai.chat_models import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain.chains import LLMChain
import google.generativeai as gemini

# External imports
from dotenv import load_dotenv
import os

# Load the environment variables
load_dotenv()


class LLM:
    """
    Singleton class for LLM

    Attributes:
    config: Configuration for the LLM
    llm: ChatOpenAI object for the LLM

    Methods:
    get_response(prompt) - get the response from the LLM
    """

    def __init__(self, llm="chatgpt"):
        """
        Constructor for the LLM class

        Args:
        llm: str - the type of LLM to be used

        """
        self.llm_type = llm

        # set the LLM based on the type
        if llm == "chatgpt":
            self.llm = ChatOpenAI(model=os.environ.get("OPENAI_MODEL"),
                                  temperature=1,
                                  api_key=os.environ.get("OPENAI_KEY"))
        elif llm == "gemini":
            gemini.configure(api_key=os.environ.get("GEMINI_API_KEY"))
            self.llm = gemini.GenerativeModel(model_name="gemini-pro")

    def change_llm_type(self, llm_type):
        """
        Change the LLM type

        Args:
        llm_type: str - the type of LLM to be used
        """
        self.llm_type = llm_type
        if llm_type == "chatgpt":
            self.llm = ChatOpenAI(model=os.environ.get("OPENAI_MODEL"),
                                  temperature=1,
                                  api_key=os.environ.get("OPENAI_KEY"))
        elif llm_type == "gemini":
            gemini.configure(api_key=os.environ.get("GEMINI_API_KEY"))
            self.llm = gemini.GenerativeModel(model_name="gemini-pro")

    def get_response(self, prompt, inputs=None):
        """
        Get the response from the LLM

        Args:
        prompt: PromptTemplate object for the prompt
        inputs: dict - dictionary containing the inputs for the LLM

        Returns:
        response: str - response from the LLM
        """

        if self.llm_type == "chatgpt":
            chain = LLMChain(llm=self.llm, prompt=prompt)
            response = chain.invoke(input=inputs)['text']
            return response
        elif self.llm_type == "gemini":
            if inputs is None:
                inputs = {}
            response = self.llm.generate_content(
                prompt.invoke(inputs).to_string(),
            )
            return response.text
