from llm.groq_llm import GroqLLM

llm = GroqLLM()

response = llm.generate(
    "What is Artificial Intelligence?"
)

print(response)