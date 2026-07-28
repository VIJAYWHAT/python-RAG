from loaders.loader import Loader
from chunking.text_chunker import TextChunker
from embeddings.embedding_model import EmbeddingModel


documents = Loader.load(
    "data/company_info/company_details.txt"
)

print(f"Loaded Documents: {len(documents)}")

chunker = TextChunker(
    chunk_size=300,
    chunk_overlap=50
)

chunks = chunker.chunk_documents(documents)

print(f"Chunks Created: {len(chunks)}")

embedding_model = EmbeddingModel()

vectors = embedding_model.embed_documents(chunks)

print(f"Vectors Generated: {len(vectors)}")
print(f"Embedding Dimension: {len(vectors[0])}")

print("\nMetadata:")
for chunk in chunks:
    print(chunk.metadata)

print("\nChunk Preview:")
for i, chunk in enumerate(chunks, start=1):
    print(f"\nChunk {i}")
    print("-" * 40)
    print(chunk.content)

print("\nFirst Embedding (First 10 Values):")
print(vectors[0][:10])