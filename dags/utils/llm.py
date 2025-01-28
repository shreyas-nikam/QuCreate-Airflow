from langchain_openai.chat_models import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain.chains.llm import LLMChain

import os
from dotenv import load_dotenv
load_dotenv()

OPEN_AI_KEY = os.getenv("OPENAI_KEY")

# Singleton class for LLM
def singleton(cls, *args, **kw):
    instances = {}
    def _singleton(*args, **kw):
        if cls not in instances:
            instances[cls] = cls(*args, **kw)
        return instances[cls]
    return _singleton

@singleton
class LLM:
    """
    Singleton class for LLM

    Attributes:
    config: Configuration for the LLM
    llm: ChatOpenAI object for the LLM

    Methods:
    get_response(prompt) - get the response from the LLM
    """
    def __init__(self):
        self.llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL"),  
                              api_key=OPEN_AI_KEY)
        
    def get_response(self, prompt, inputs={}):
        # Create the chain
        chain = LLMChain(llm=self.llm, prompt=PromptTemplate.from_template(prompt))
        # Get the response
        response = chain.invoke(input=inputs)['text']
        return response
