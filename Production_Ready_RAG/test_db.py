from loaders.loader import Loader
from chunking.text_chunker import TextChunker
from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase

loader = Loader()
documents = loader.load(
    "data/company_info/company_details.txt"
)

chunker = TextChunker(
    chunk_size=300,
    chunk_overlap=50
)

chunks = chunker.chunk_documents(documents)

embedding_model = EmbeddingModel()

vectors = embedding_model.embed_documents(chunks)

print(f"Documents : {len(documents)}")
print(f"Chunks    : {len(chunks)}")
print(f"Vectors   : {len(vectors)}")

db = VectorDatabase()
db.reset_collection()

db.add_documents(chunks, vectors)
results = db.collection.get()

print("Count:", db.count())
print("Stored IDs:", len(results["ids"]))
print("IDs:", results["ids"])

print("Documents stored successfully.")
