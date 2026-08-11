from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase
from retriever.retriever import Retriever
from llm.groq_llm import GroqLLM
from context_checker.context_checker import ContextChecker


embedding_model = EmbeddingModel()

vector_db = VectorDatabase()

retriever = Retriever(
    embedding_model,
    vector_db
)

checker_llm = GroqLLM(
    model="llama-3.1-8b-instant"
)

context_checker = ContextChecker(
    llm=checker_llm
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

    documents = retriever.retrieve(
        query=question,
        k=3
    )

    answerable = context_checker.is_answerable(
        question=question,
        documents=documents
    )

    print("Answerable:", answerable)