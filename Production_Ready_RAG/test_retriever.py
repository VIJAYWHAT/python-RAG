from embeddings.embedding_model import EmbeddingModel
from retriever.retriever import Retriever
from vectordb.chroma_db import VectorDatabase

embedding_model = EmbeddingModel()
vector_db = VectorDatabase()

retriever = Retriever(
    embedding_model=embedding_model,
    vector_db=vector_db
)

documents = retriever.retrieve(
    "Where is the company headquarters?"
)

for index, document in enumerate(documents, start=1):

    print(f"\nResult {index}")
    print("-" * 50)
    print(document.content)
    print(document.metadata)