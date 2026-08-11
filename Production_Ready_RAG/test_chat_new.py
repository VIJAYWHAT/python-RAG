from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase
from retriever.retriever import Retriever
from prompts.prompt_builder import PromptBuilder
from llm.groq_llm import GroqLLM
from memory.chat_memory import ChatMemory
from chat.chat_service import ChatService
from query_rewriter.query_rewriter import QueryRewriter
from guardrails.guardrail_service import GuardrailService
from guardrails.guardrail_logger import GuardrailLogger
from context_checker.context_checker import ContextChecker
from hr_queries.hr_query_store import HRQueryStore


# Initialize Components
embedding_model = EmbeddingModel()
vector_db = VectorDatabase()


retriever = Retriever(
    embedding_model,
    vector_db
)

prompt_builder = PromptBuilder()

rewrite_llm = GroqLLM(
    model="llama-3.1-8b-instant"
)

answer_llm = GroqLLM(
    model="llama-3.3-70b-versatile"
)

query_rewriter = QueryRewriter(
    llm=rewrite_llm
)

memory = ChatMemory()
guardrails = GuardrailService()
guardrail_logger = GuardrailLogger()

context_checker = ContextChecker(
    llm=rewrite_llm
)

hr_query_store = HRQueryStore()

chat = ChatService(
    retriever=retriever,
    prompt_builder=prompt_builder,
    llm=answer_llm,
    memory=memory,
    query_rewriter=query_rewriter,
    guardrails=guardrails,
    guardrail_logger=guardrail_logger,
    context_checker=context_checker,
    hr_query_store=hr_query_store
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

    print("=" * 70)
    print("AI Response")
    print("=" * 70)
    print(response.answer)

    if response.llm_response:
        print()
        print("Prompt Tokens      : ", response.llm_response.prompt_tokens)
        print("Completion Tokens  : ", response.llm_response.completion_tokens)
        print("Total Tokens       : ", response.llm_response.total_tokens)

    else:
        print()
        print("LLM Tokens         : N/A")
        print("Reason             : LLM was not called")

    # print("\nConversation History")
    # print("=" * 70)

    # for message in memory.get_messages():
    #     print(f"{message['role'].capitalize()}: {message['content']}")
    
    if response.source_documents:

        print()
        print("# Sources")
        print()

        for document in response.source_documents:

            source = document.metadata.get(
                "source",
                "Unknown"
            )

            print("-", source)

    if response.guardrail_status != "allow":

        print()
        print("# Guardrail")
        print()
        print("Status :", response.guardrail_status)
        print("Reason :", response.guardrail_reason) 