from retriever.retriever import Retriever
from prompts.prompt_builder import PromptBuilder
from llm.groq_llm import GroqLLM
from memory.chat_memory import ChatMemory

class ChatService:

    def __init__(
        self,
        retriever,
        prompt_builder,
        llm,
        memory: ChatMemory
    ):

        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.llm = llm
        self.memory = memory
        
    def ask(
        self,
        question: str
    ) -> str:

        self.memory.add_user_message(question)

        documents = self.retriever.retrieve(question)

        prompt = self.prompt_builder.build_prompt(
            question,
            documents
        )

        response = self.llm.generate(prompt)

        self.memory.add_assistant_message(response)

        return response