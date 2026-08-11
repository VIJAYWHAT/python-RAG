from langdetect import detect, LangDetectException


class LanguageDetector:

    SUPPORTED_LANGUAGES = {
        "en": "English",
        "hi": "Hindi",
        "ur": "Urdu",
        "ar": "Arabic",
        "ml": "Malayalam",
        "ta": "Tamil",
        "bn": "Bengali"
    }

    def detect_language(
        self,
        text: str
    ) -> str:

        try:

            language_code = detect(text)

            return self.SUPPORTED_LANGUAGES.get(
                language_code,
                "English"
            )

        except LangDetectException:

            return "English"