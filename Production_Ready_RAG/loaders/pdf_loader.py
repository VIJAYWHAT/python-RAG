from pathlib import Path
from typing import List

from pypdf import PdfReader

from models.document import Document


class PDFLoader:
    """
    Loader for PDF files.
    """

    @staticmethod
    def load(file_path: str) -> List[Document]:
        """
        Reads a PDF file and returns one Document object per page.
        """

        path = Path(file_path)

        reader = PdfReader(path)

        documents = []

        for page_number, page in enumerate(reader.pages, start=1):

            text = page.extract_text()

            # Skip completely blank pages
            if not text:
                continue

            document = Document(
                content=text,
                metadata={
                    "source": str(path),
                    "file_name": path.name,
                    "file_type": "pdf",
                    "page": page_number
                }
            )

            documents.append(document)

        return documents