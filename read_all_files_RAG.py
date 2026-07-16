import os
import pandas as pd
from pypdf import PdfReader
from docx import Document

def load_company_documents(folder_path):
    all_content = ""

    for file_name in os.listdir(folder_path):

        file_path = os.path.join(folder_path, file_name)

        print(f"Loading: {file_name}")

        # TXT
        if file_name.endswith(".txt"):
            with open(file_path, "r", encoding="utf-8") as f:
                all_content += f"\n\n----- {file_name} -----\n"
                all_content += f.read()

        # PDF
        elif file_name.endswith(".pdf"):
            reader = PdfReader(file_path)

            text = ""

            for page in reader.pages:
                text += page.extract_text() or ""

            all_content += f"\n\n----- {file_name} -----\n"
            all_content += text

        # DOCX
        elif file_name.endswith(".docx"):

            doc = Document(file_path)

            text = "\n".join(
                para.text
                for para in doc.paragraphs
            )

            all_content += f"\n\n----- {file_name} -----\n"
            all_content += text

        # CSV
        elif file_name.endswith(".csv"):
            df = pd.read_csv(file_path)
            text = df.to_string(index=False)

            all_content += f"\n\n----- {file_name} -----\n"
            all_content += text

        # XLSX
        elif file_name.endswith(".xlsx"):

            excel = pd.ExcelFile(file_path)

            text = ""

            for sheet in excel.sheet_names:

                df = pd.read_excel(file_path, sheet_name=sheet)

                text += f"\nSheet: {sheet}\n"

                text += df.to_string(index=False)

            all_content += f"\n\n----- {file_name} -----\n"
            all_content += text

    return all_content

from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)
company_details = load_company_documents("company_details")
messages = [
    {
        "role": "system",
        "content": f"""
You are an HR representative of Usis Technologies.

Use the following company information to answer all questions.
If the answer is not present in this information, say you don't know.

{company_details}
"""
    }
]

print("Type 'exit' to quit.\n")

while True:

    user_input = input("You: ")

    if user_input.lower() == "exit":
        break

    messages.append(
        {
            "role": "user",
            "content": user_input
        }
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=200
    )

    assistant_reply = response.choices[0].message.content

    print("AI:", assistant_reply)
    print()

    messages.append(
        {
            "role": "assistant",
            "content": assistant_reply
        }
    )
    print()
    print("Prompt Tokens:", response.usage.prompt_tokens)
    print("Completion Tokens:", response.usage.completion_tokens)
    print("Total Tokens:", response.usage.total_tokens)
