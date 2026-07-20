from pathlib import Path
from typing import List

import pandas as pd

from models.document import Document


class SpreadsheetLoader:
    """
    Loader for CSV and Excel (.xls, .xlsx) files.
    """

    @staticmethod
    def load(file_path: str) -> List[Document]:
        """
        Reads CSV or Excel files and returns one Document per sheet.
        """

        path = Path(file_path)

        documents = []

        # ---------------- CSV ---------------- #

        if path.suffix.lower() == ".csv":

            df = pd.read_csv(path)

            content = df.to_string(index=False)

            documents.append(
                Document(
                    content=content,
                    metadata={
                        "source": str(path),
                        "file_name": path.name,
                        "file_type": "csv",
                        "sheet_name": "CSV"
                    }
                )
            )

        # ---------------- Excel (.xls / .xlsx) ---------------- #

        elif path.suffix.lower() in [".xls", ".xlsx"]:

            excel = pd.ExcelFile(path)

            for sheet in excel.sheet_names:

                df = pd.read_excel(path, sheet_name=sheet)

                content = df.to_string(index=False)

                documents.append(
                    Document(
                        content=content,
                        metadata={
                            "source": str(path),
                            "file_name": path.name,
                            "file_type": path.suffix.lower().replace(".", ""),
                            "sheet_name": sheet
                        }
                    )
                )

        return documents