from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase
from typing import List
from models.document import Document

class Retriever:

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        vector_db: VectorDatabase
    ):

        self.embedding_model = embedding_model
        self.vector_db = vector_db
        
    def retrieve(
        self,
        query: str,
        k: int = 3
    ) -> List[Document]:

        query_embedding = self.embedding_model.embed_query(query)

        documents = self.vector_db.similarity_search(
            query_embedding=query_embedding,
            n_results=k
        )

        return documents