from loaders.txt_loader import TXTLoader

doc = TXTLoader.load("company_details/Company_Details_.txt")

print(doc)

print()

print(doc.content[:400])

print()

print(doc.metadata)