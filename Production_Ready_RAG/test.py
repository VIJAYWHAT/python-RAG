from loaders.pdf_loader import PDFLoader

documents = PDFLoader.load(
    "company_details/Employee_Policy_Handbook.pdf"
)

print(f"Total Pages Loaded: {len(documents)}")

for document in documents:

    print(document)

    print(document.content[:200])

    print(document.metadata)

    print("-" * 50)