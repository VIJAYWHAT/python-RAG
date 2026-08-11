from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase
from retriever.retriever import Retriever


embedding_model = EmbeddingModel()

vector_db = VectorDatabase()

retriever = Retriever(
    embedding_model,
    vector_db
)


questions = [

    "What is the leave policy?",

    "What is casual leave?",

    "What is the company policy for XYZ benefit?",

    "What is the employee maternity policy?",

    "What is the company's office location?"
]


for question in questions:

    print()
    print("=" * 70)
    print("Question:", question)
    print("=" * 70)

    results = retriever.retrieve_with_scores(
        query=question,
        k=3
    )

    for index, result in enumerate(
        results,
        start=1
    ):

        document = result["document"]
        distance = result["distance"]

        print()
        print(f"Result {index}")

        print(
            "Distance:",
            distance
        )

        print(
            "Source:",
            document.metadata.get(
                "source",
                "Unknown"
            )
        )

        print(
            "Content:",
            document.content[:200]
        )