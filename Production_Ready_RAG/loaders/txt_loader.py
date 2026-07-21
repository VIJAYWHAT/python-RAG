from pathlib import Path

from models.document import Document


class TXTLoader:
    """
    Loader for TXT files.
    """

    @staticmethod
    def load(file_path: str) -> Document:
        """
        Reads a TXT file and returns a Document object.
        """

        path = Path(file_path)

        with open(path, "r", encoding="utf-8") as file:
            text = file.read()

        metadata = {
            "source": str(path),
            "file_name": path.name,
            "file_type": "txt"
        }

        return Document(
            content=text,
            metadata=metadata
        )