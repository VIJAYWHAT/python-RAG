from abc import ABC, abstractmethod


class BaseLLM(ABC):

    @abstractmethod
    def generate(
        self,
        messages: list,
        temperature: float = 0.2,
        max_tokens: int = 1024
    ) -> str:
        """
        Generate a response from the LLM.
        """
        pass