from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase


def main():

    embedding_model = EmbeddingModel()

    vector_db = VectorDatabase(
        persist_directory="data/vector_db",
        collection_name="hr_knowledge_base"
    )

    questions = [
        "What is the leave policy?",
        "What is casual leave?",
        "Where is the company located?",
        "What services does the company provide?",
        "What is the employee policy?",
        "Who are the employees?"
    ]

    for question in questions:

        print()
        print("=" * 70)
        print(
            f"Question: {question}"
        )
        print("=" * 70)

        query_embedding = (
            embedding_model.embed_query(
                question
            )
        )

        results = vector_db.similarity_search(
            query_embedding=query_embedding,
            n_results=3
        )

        for index, document in enumerate(
            results,
            start=1
        ):

            print()
            print(
                f"Result {index}"
            )

            print(
                f"Distance: "
                f"{document.metadata.get('distance')}"
            )

            print(
                f"Source: "
                f"{document.metadata.get('source')}"
            )

            print(
                f"Chunk: "
                f"{document.metadata.get('chunk_id')}"
            )

            print(
                f"Content: "
                f"{document.content[:500]}"
            )


if __name__ == "__main__":

    main()