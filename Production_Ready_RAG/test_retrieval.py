from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase

embedding_model = EmbeddingModel()
db = VectorDatabase()

query = "Where is the company headquarters?"

query_vector = embedding_model.embed_query(query)

results = db.similarity_search(
    query_embedding=query_vector,
    n_results=3
)
print("Query:", query)
print()
print("Results:", results)