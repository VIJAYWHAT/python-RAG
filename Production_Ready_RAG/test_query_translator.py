from llm.groq_llm import GroqLLM
from language.query_translator import QueryTranslator


llm = GroqLLM(
    model="llama-3.1-8b-instant"
)

translator = QueryTranslator(
    llm=llm
)


questions = [

    "What is the leave policy?",

    "छुट्टी की नीति क्या है?",

    "விடுப்பு கொள்கை என்ன?",

    "അവധിയുടെ നയം എന്താണ്?",

    "ما هي سياسة الإجازات؟",

    "কোম্পানির ছুটির নীতি কী?"
]


for question in questions:

    result = translator.translate_to_english(
        question
    )

    print("=" * 70)
    print("Original :", question)
    print("English  :", result)