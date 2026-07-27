from typing import List

from models.document import Document


class TextChunker:
    """
    Splits documents into smaller overlapping chunks.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ):

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_documents(
        self,
        documents: List[Document]
    ) -> List[Document]:

        chunked_documents = []

        for document in documents:

            chunks = self.split_text(document)

            chunked_documents.extend(chunks)

        return chunked_documents

    def split_text(
        self,
        document: Document
    ) -> List[Document]:

        content = document.content

        metadata = document.metadata

        chunks = []

        start = 0

        chunk_number = 1

        while start < len(content):

            end = start + self.chunk_size

            chunk_text = content[start:end]

            chunk_metadata = metadata.copy()

            chunk_metadata["chunk"] = chunk_number

            chunks.append(
                Document(
                    content=chunk_text,
                    metadata=chunk_metadata
                )
            )

            start = end - self.chunk_overlap

            chunk_number += 1

        return chunks