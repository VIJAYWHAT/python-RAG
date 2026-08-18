from typing import List

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter
)

from models.document import Document


class TextChunker:
    """
    Splits documents into smaller overlapping chunks
    using LangChain's RecursiveCharacterTextSplitter.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ):

        self.text_splitter = (
            RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        )

    def chunk_documents(
        self,
        documents: List[Document]
    ) -> List[Document]:

        chunked_documents = []

        for document in documents:

            chunks = self.text_splitter.split_text(
                document.content
            )

            for index, chunk in enumerate(
                chunks,
                start=1
            ):

                metadata = document.metadata.copy()

                metadata["chunk_id"] = index

                chunked_documents.append(
                    Document(
                        content=chunk,
                        metadata=metadata
                    )
                )

        return chunked_documents