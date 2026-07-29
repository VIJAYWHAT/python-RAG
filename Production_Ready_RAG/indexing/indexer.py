from pathlib import Path

from loaders.loader import Loader
from chunking.text_chunker import TextChunker
from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase


class Indexer:

    def __init__(
        self,
        loader: Loader,
        chunker: TextChunker,
        embedding_model: EmbeddingModel,
        vector_db: VectorDatabase
    ):

        self.loader = loader
        self.chunker = chunker
        self.embedding_model = embedding_model
        self.vector_db = vector_db

    def index_directory(
        self,
        directory: str
    ):

        supported_extensions = {
            ".txt",
            ".pdf",
            ".docx"
        }

        for file_path in Path(directory).iterdir():

            if (
                file_path.is_file()
                and file_path.suffix.lower() in supported_extensions
            ):

                print(f"Indexing: {file_path.name}")

                documents = self.loader.load(
                    str(file_path)
                )

                chunks = self.chunker.chunk_documents(
                    documents
                )

                vectors = self.embedding_model.embed_documents(
                    chunks
                )

                self.vector_db.add_documents(
                    chunks,
                    vectors
                )

        print("Indexing Completed.")