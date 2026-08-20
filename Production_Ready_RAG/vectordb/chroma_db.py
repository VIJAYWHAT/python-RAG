import chromadb

from typing import List

from models.document import Document


class VectorDatabase:

    def __init__(
        self,
        persist_directory: str = "data/vector_db",
        collection_name: str = "hr_knowledge_base"
    ):

        self.client = chromadb.PersistentClient(
            path=persist_directory
        )
        
        self.collection_name = collection_name

        self.collection = (
            self.client.get_or_create_collection(
                name=collection_name
            )
        )

    def add_documents(
        self,
        documents: List[Document],
        embeddings: List[List[float]]
    ):

        if not documents:
            return

        ids = []
        texts = []
        metadatas = []

        for index, document in enumerate(
            documents
        ):

            source = document.metadata.get(
                "source",
                "unknown"
            )

            chunk_id = document.metadata.get(
                "chunk_id",
                index
            )

            document_id = (
                f"{source}_{chunk_id}"
            )

            document_id = (
                document_id
                .replace("\\", "_")
                .replace("/", "_")
                .replace(" ", "_")
            )

            ids.append(document_id)
            texts.append(document.content)
            metadatas.append(document.metadata)

        self.collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas
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

        result_documents = results.get(
            "documents",
            [[]]
        )[0]

        result_metadatas = results.get(
            "metadatas",
            [[]]
        )[0]

        result_distances = results.get(
            "distances",
            [[]]
        )[0]

        for index, content in enumerate(
            result_documents
        ):

            metadata = (
                result_metadatas[index] or {}
            )

            metadata["distance"] = (
                result_distances[index]
            )

            documents.append(
                Document(
                    content=content,
                    metadata=metadata
                )
            )

        return documents
    
    def reset_collection(self):

        try:
            self.client.delete_collection(
                name=self.collection_name
            )

            self.collection = (
                self.client.get_or_create_collection(
                    name=self.collection_name
                )
            )

            print(
                f"Collection '{self.collection_name}' "
                "reset successfully."
            )

        except Exception as error:

            print(
                f"Error resetting collection: {error}"
            )

            raise