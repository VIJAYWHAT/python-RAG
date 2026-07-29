from loaders.loader import Loader
from chunking.text_chunker import TextChunker
from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase
from indexing.indexer import Indexer

loader = Loader()
chunker = TextChunker()
embedding_model = EmbeddingModel()
vector_db = VectorDatabase()

indexer = Indexer(
    loader,
    chunker,
    embedding_model,
    vector_db
)

indexer.index_directory(
    "data/company_info"
)