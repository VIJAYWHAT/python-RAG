from loaders.loader import Loader
from chunking.text_chunker import TextChunker

documents = Loader.load(
    "Production_Ready_RAG/data/company_info/Company_Profile.docx"
)

chunker = TextChunker(
    chunk_size=100,
    chunk_overlap=20
)

chunks = chunker.split_documents(documents)

print(f"Total Chunks: {len(chunks)}")

for chunk in chunks:

    print(chunk.metadata)

    print(chunk.content)

    print("-" * 50)