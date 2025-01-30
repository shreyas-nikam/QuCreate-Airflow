import os
import pinecone
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.schema import Document
import uuid
import os
from dotenv import load_dotenv

load_dotenv()



# Initialize Pinecone
pinecone.init(api_key=os.getenv("PINECONE_API_KEY"), environment='us-west1-gcp')

# Define the index name
index_name = 'chatbot-vector-store'

# Check if the index exists; if not, create it
if index_name not in pinecone.list_indexes():
    pinecone.create_index(index_name, dimension=1536)  # 1536 is the dimensionality of OpenAI's embeddings

# Connect to the index
index = pinecone.Index(index_name)

def create_vector_store(file_path):
    # Generate a unique file ID
    file_id = str(uuid.uuid4())

    # Load your text file
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # Split the content into chunks
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    texts = text_splitter.split_text(content)

    # Create Document objects
    docs = [Document(page_content=text) for text in texts]

    # Initialize the OpenAI Embeddings model
    embedding = OpenAIEmbeddings()

    # Generate embeddings and prepare data for upsert
    data = []
    for i, doc in enumerate(docs):
        embedding_vector = embedding.embed_query(doc.page_content)
        data.append((f'{file_id}_doc_{i}', embedding_vector, {'file_id': file_id}))

    # Upsert data into Pinecone index under the specified namespace
    index.upsert(vectors=data, namespace=file_id)

    return file_id

# Example usage
file_id = create_vector_store('your_text_file.txt')
print(f'File ID: {file_id}')
