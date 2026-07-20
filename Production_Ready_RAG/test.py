from loaders.loader import Loader

documents = Loader.load(
    "Production_Ready_RAG/data/company_info/Employees.csv"
)

print(f"Loaded {len(documents)} document(s)\n")

for doc in documents:

    print(doc)

    print(doc.metadata)

    print(doc.content[:200])

    print("-" * 50)