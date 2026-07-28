from typing import List
from sentence_transformers import SentenceTransformer
from models.document import Document


class EmbeddingModel:

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2"
    ):
        self.model = SentenceTransformer(model_name)

    def embed_text(self, text: str):
        return self.model.encode(text)

    def embed_documents(self, documents: List[Document]):
        texts = [
            document.content
            for document in documents
        ]

        return self.model.encode(texts)
    
    def embed_query(
        self,
        query: str
    ):
        return self.model.encode(query).tolist()