from pathlib import Path

from loaders.loader import Loader
from chunking.text_chunker import TextChunker
from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase

# Initialize loader
loader = Loader()

# Folder containing all documents
DATA_FOLDER = Path("data/company_info")

# Supported file extensions
SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx", ".csv"}

# Load all documents
documents = []

for file_path in DATA_FOLDER.iterdir():
    if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
        print(f"Loading: {file_path.name}")

        try:
            docs = loader.load(str(file_path))
            documents.extend(docs)
        except Exception as e:
            print(f"Failed to load {file_path.name}: {e}")

print(f"\nTotal files loaded: {len(documents)}")

# Chunk documents
chunker = TextChunker(
    chunk_size=300,
    chunk_overlap=50
)

chunks = chunker.chunk_documents(documents)
# Store in ChromaDB
db = VectorDatabase()

# Clear previous collection
db.reset_collection()
print(f"Collection '{db.collection.name}' has been reset.")
# Generate embeddings
embedding_model = EmbeddingModel()
vectors = embedding_model.embed_documents(chunks)

print(f"Documents : {len(documents)}")
print(f"Chunks    : {len(chunks)}")
print(f"Vectors   : {len(vectors)}")



# # Add new documents
# db.add_documents(chunks, vectors)

# results = db.collection.get()

# print(f"\nCount      : {db.count()}")
# print(f"Stored IDs : {len(results['ids'])}")
# print(f"IDs        : {results['ids']}")

# print("\nAll documents stored successfully.")