from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase
from retriever.retriever import Retriever
from prompts.prompt_builder import PromptBuilder
from llm.groq_llm import GroqLLM
from chat.chat_service import ChatService


# Initialize Components
embedding_model = EmbeddingModel()

vector_db = VectorDatabase()

retriever = Retriever(
    embedding_model,
    vector_db
)

prompt_builder = PromptBuilder()

llm = GroqLLM()

chat = ChatService(
    retriever,
    prompt_builder,
    llm
)


print("=" * 60)
print("Production Ready RAG Chat")
print("Type 'exit' to quit.")
print("=" * 60)

while True:

    question = input("\nYou : ").strip()

    if question.lower() == "exit":
        print("\nGoodbye!")
        break

    response = chat.ask(question)

    print(f"\nAI  : {response}")