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

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {
            "role": "system",
            "content": "You are a HR of Usis Technologies."
        },
        {
            "role": "system",
            "content": company_details
        },
        
        {
        "role": "system",
        "content": f"""
You are an HR representative of Usis Technologies.

Use the following company information to answer all questions.
If the answer is not present in this information, say you don't know.

{company_details}
"""
    },
        
        {
            "role": "user",
            "content": "How many employees working in your company?"
        }
    ],
    # max_completion_tokens=200
    max_tokens=200
    # temperature=1,
    # top_p=1,
    # stream=True,
    # stream_options={"include_usage": True},
    # stop=None
)

print("Reply:")
print(response.choices[0].message.content)

print()
print("Prompt Tokens:", response.usage.prompt_tokens)
print("Completion Tokens:", response.usage.completion_tokens)
print("Total Tokens:", response.usage.total_tokens)

# # This is used while using a stream.
# usage = None
# print("Reply:")
# for chunk in response:
#     if chunk.choices:
#         print(chunk.choices[0].delta.content or "", end="")

#     if chunk.usage:
#         usage = chunk.usage
# print()
# if usage:
#     print("Prompt Tokens:", usage.prompt_tokens)
#     print("Completion Tokens:", usage.completion_tokens)
#     print("Total Tokens:", usage.total_tokens)