from loaders.loader import Loader
from chunking.text_chunker import TextChunker

documents = Loader.load(
    "Production_Ready_RAG/data/company_info/company_details.txt"
)

chunker = TextChunker(
    chunk_size=800,
    chunk_overlap=50
)

chunks = chunker.split_documents(documents)

print(f"Total Chunks: {len(chunks)}\n")

for chunk in chunks:

    print(chunk.metadata)

    print(chunk.content)

    print("-" * 50)