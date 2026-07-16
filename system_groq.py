from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages = [
    {
        "role": "system",
        "content": """
You are an HR Representative of uSiS Technologies.

Answer only questions related to uSiS Technologies using the company information provided below.
If the answer is not available, politely respond:
"I'm sorry, I don't have that information."

Use the following company information to answer all questions.
If the answer is not present in this information, say you don't know.

Do not guess or make up information.
Keep your responses professional, friendly, and concise.

Company Information:

Company Name: uSiS Technologies

Headquarters:
Coimbatore, Tamil Nadu, India

Founded:
2007

About:
uSiS Technologies is an IT consulting and software development company that provides digital transformation solutions for startups, SMEs, and enterprises.

Services:
- Custom Software Development
- Web & Mobile Application Development
- AI Solutions
- ERP & HRMS Solutions
- Business Process Automation
- IT Consulting
- Team Augmentation
- Product Engineering

Industries Served:
Retail, Manufacturing, Healthcare, Banking & Finance, Hospitality, Real Estate, Human Resources, IT, and Education.

Technology Stack:
.NET, React, Angular, Node.js, PHP, Flutter, Python, MySQL, MongoDB, ERPNext, Frappe HR, Azure AI.
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
