from typing import List
import uuid

from chromadb import PersistentClient
from models.document import Document



class VectorDatabase:

    def __init__(
        self,
        db_path: str = "./database",
        collection_name: str = "company_documents"
    ):

        self.client = PersistentClient(path=db_path)

        self.collection = self.client.get_or_create_collection(
            name=collection_name
        )

    def add_documents(
        self,
        documents: List[Document],
        embeddings
    ):

        ids = [
            str(uuid.uuid4())
            for _ in documents
        ]

        texts = [
            document.content
            for document in documents
        ]

        metadata = [
            document.metadata
            for document in documents
        ]

        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadata
        )
        print(f"IDs        : {len(ids)}")
        print(f"Texts      : {len(texts)}")
        print(f"Metadata   : {len(metadata)}")
        print(f"Embeddings : {len(embeddings)}")
        
    def count(self):
        return self.collection.count()
    
    def reset_collection(self):
        self.client.delete_collection("company_documents")
        self.collection = self.client.get_or_create_collection(
            name="company_documents"
        )
    
    def similarity_search(
        self,
        query_embedding: List[float],
        n_results: int = 3
    ) -> List[Document]:

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )

        documents = []

        for text, metadata, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):

            metadata = metadata.copy()
            metadata["distance"] = distance

            documents.append(
                Document(
                    content=text,
                    metadata=metadata
                )
            )

        return documents