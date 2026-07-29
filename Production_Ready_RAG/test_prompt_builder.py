from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase
from retriever.retriever import Retriever
from prompts.prompt_builder import PromptBuilder

embedding_model = EmbeddingModel()
vector_db = VectorDatabase()

retriever = Retriever(
    embedding_model,
    vector_db
)

documents = retriever.retrieve(
    "Where is the company headquarters?"
)

builder = PromptBuilder()

prompt = builder.build_prompt(
    "Where is the company headquarters?",
    documents
)

print(prompt)