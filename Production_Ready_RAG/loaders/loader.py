from pathlib import Path
from typing import List

from models.document import Document
from loaders.txt_loader import TXTLoader
from loaders.pdf_loader import PDFLoader
from loaders.docx_loader import DOCXLoader
from loaders.spreadsheet_loader import SpreadsheetLoader


class Loader:
    """
    Main document loader.

    Automatically detects the file type and delegates
    the loading process to the appropriate loader.
    """

    @staticmethod
    def load(file_path: str) -> List[Document]:

        path = Path(file_path)

        extension = path.suffix.lower()

        if extension == ".txt":
            return [TXTLoader.load(file_path)]

        elif extension == ".pdf":
            return PDFLoader.load(file_path)

        elif extension == ".docx":
            return [DOCXLoader.load(file_path)]

        elif extension in [".csv", ".xls", ".xlsx"]:
            return SpreadsheetLoader.load(file_path)

        raise ValueError(f"Unsupported file type: {extension}")
    