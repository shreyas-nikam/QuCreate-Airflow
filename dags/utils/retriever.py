from pathlib import Path
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.retrievers.document_compressors import CohereRerank
from langchain.retrievers import ContextualCompressionRetriever
from langchain.docstore.document import Document
from dotenv import load_dotenv
import os
import pickle
from utils.json_handler import JSONHandler

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

def singleton(cls, *args, **kw):
    instances = {}
    def _singleton(*args, **kw):
        if cls not in instances:
            instances[cls] = cls(*args, **kw)
        return instances[cls]
    return _singleton

@singleton
class Retriever:
    def __init__(self):        
        # Initialize the retrievers
        self.bm25_retriever = None
        self.vector_store = None
        self.faiss_retriever = None

        self.embeddings = OpenAIEmbeddings(api_key=OPENAI_API_KEY)
        
        # Initialize the re_ranker
        self.re_ranker = CohereRerank(cohere_api_key=COHERE_API_KEY)

        self.params_loaded = False

        self.db_path = "output/retriever"

    def create_vector_store(self, file_content, db_path="output/retriever"):
        # Load the documents
        documents = file_content
        docs = []
        
        for i in range(0, len(documents), 20000):
            doc = documents[i:i+20000]
            docs.append(Document(page_content=doc))

        # Create the vector store
        self.vector_store = FAISS.from_documents(docs, self.embeddings)

        # Save the vector store
        self.vector_store.save_local(Path(str(db_path)+"/hybrid_db"))
        self.db_path = db_path

        # Create the retriever
        self.bm25_retriever = BM25Retriever.from_documents(docs)
        self.bm25_retriever.k=5

        self._save_params(folder_name=db_path)
        self.params_loaded = True

    def _save_params(self, folder_name='inputs/retriever'):
        # Store the retrievers and vector store to be used later
        with open(f"{folder_name}/bm25_retriever.pkl", "wb") as f:
            pickle.dump(self.bm25_retriever, f)
        with open(f"{folder_name}/faiss_retriever.pkl", "wb") as f:
            pickle.dump(self.faiss_retriever, f)

    def _load_params(self, folder_name='inputs/retriever'):
        # Load the embeddings, retrievers and vector store which were saved earlier
        self.embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
        self.vector_store = FAISS.load_local(self.db_path, self.embeddings)
        self.re_ranker = CohereRerank(cohere_api_key=COHERE_API_KEY)

        with open(f"{folder_name}/bm25_retriever.pkl", "rb") as f:
            self.bm25_retriever = pickle.load(f)
        with open(f"{folder_name}/faiss_retriever.pkl", "rb") as f:
            self.faiss_retriever = pickle.load(f)

        # Load the retrievers for use
        faiss_retriever = self.vector_store.as_retriever(search_kwargs={"k": 5})
        ensemble_retriever = EnsembleRetriever(
            retrievers=[self.bm25_retriever, faiss_retriever], 
            weights=[0.5, 0.5]
        )

        self.compression_retriever = ContextualCompressionRetriever(
            base_compressor=self.re_ranker, 
            base_retriever=ensemble_retriever
        )
        
        self.params_loaded = True


    def _retrieve_with_rerank(self, query):
        # Load the retrievers if they are not loaded
        if self.params_loaded == False:
            self._load_params()
        
        # Get the response
        response = self.compression_retriever.invoke(query)
        return response
    
    def parse_response_with_rerank(self, query):
        # Get the response
        response = self._retrieve_with_rerank(query)
        
        # Parse and return the response
        return ' '.join([r.page_content for r in response])
    


if __name__=="__main__":
    retriever = Retriever()
    retriever.create_vector_store(file_name="/Users/zeronp/Downloads/QuantUniversityProjects/Coursify2/inputs/content.txt")