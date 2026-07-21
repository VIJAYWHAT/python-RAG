from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class Document:
    """
    Represents a single document or document chunk in the RAG pipeline.
    """

    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self):
        return (
            f"Document("
            f"source={self.metadata.get('source', 'Unknown')}, "
            f"content_length={len(self.content)}"
            f")"
        )