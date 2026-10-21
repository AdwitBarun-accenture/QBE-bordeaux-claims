"""Provider-agnostic LLM interface. Agents only ever call LLMClient.complete();
switching between Claude (direct or via Azure Foundry) and Azure OpenAI is a
config change (LLM_PROVIDER)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMUnavailable(Exception):
    """Raised when no provider is configured or the call failed after retries.
    Every agent catches this and falls back to deterministic logic."""


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 1500, temperature: float = 0.0) -> LLMResponse: ...
