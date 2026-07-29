from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase
from retriever.retriever import Retriever
from prompts.prompt_builder import PromptBuilder
from llm.groq_llm import GroqLLM
from memory.chat_memory import ChatMemory
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

memory = ChatMemory()

chat = ChatService(
    retriever,
    prompt_builder,
    llm,
    memory
)


print("=" * 70)
print("Production Ready RAG Chat")
print("Type 'exit' to quit.")
print("=" * 70)

while True:

    question = input("\nYou : ")

    if question.lower() == "exit":
        print("\nExiting chat...")
        break

    response = chat.ask(question)

    print("\nAI Response")
    print("=" * 70)
    print(response)

    print("\nConversation History")
    print("=" * 70)

    for message in memory.get_messages():
        print(f"{message['role'].capitalize()}: {message['content']}")