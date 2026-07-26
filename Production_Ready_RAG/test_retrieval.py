from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase

embedding_model = EmbeddingModel()
db = VectorDatabase()

query = "Where is the company headquarters?"

query_vector = embedding_model.embed_query(query)

documents = db.similarity_search(query_vector)

print(f"Query: {query}")
for index, document in enumerate(documents, start=1):
    print(f"\nResult {index}")
    print("-" * 50)
    print(document.content)
    print(document.metadata)