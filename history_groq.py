from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)
with open("company_details.txt", "r", encoding="utf-8") as f:
    company_details = f.read()
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