"""LLMClient = provider + JSON parsing + audit logging (tokens, latency, model)
into Operational Memory for every call."""
from functools import lru_cache

from app.core.config import get_settings
from app.llm.base import LLMProvider, LLMResponse, LLMUnavailable
from app.llm.providers import AnthropicFoundryProvider, AnthropicProvider, AzureOpenAIProvider, NoneProvider
from app.utils.json_utils import extract_json
from app.utils.logging import get_logger
from app.utils.timing import Stopwatch

log = get_logger(__name__)


@lru_cache
def get_provider() -> LLMProvider:
    s = get_settings()
    try:
        return {"anthropic": AnthropicProvider, "anthropic_foundry": AnthropicFoundryProvider,
                "azure_openai": AzureOpenAIProvider}.get(s.llm_provider, lambda _s: NoneProvider())(s)
    except LLMUnavailable as e:
        log.warning(f"LLM provider not available ({e}); using deterministic fallbacks")
        return NoneProvider()


class LLMClient:
    def __init__(self, recorder=None):
        """recorder: callable(action, detail, model, in_tok, out_tok, ms) -> writes operational log."""
        self.provider = get_provider()
        self.recorder = recorder

    @property
    def available(self) -> bool:
        return not isinstance(self.provider, NoneProvider)

    def text(self, purpose: str, system: str, user: str, max_tokens: int = 1000) -> LLMResponse:
        sw = Stopwatch()
        try:
            resp = self.provider.complete(system, user, max_tokens=max_tokens)
        except LLMUnavailable:
            raise
        except Exception as e:  # network, auth, rate limit after retries
            log.exception("LLM call failed")
            if self.recorder:
                self.recorder(f"LLM call failed: {purpose}", str(e)[:500], "", 0, 0, sw.ms)
            raise LLMUnavailable(str(e)) from e
        if self.recorder:
            self.recorder(f"LLM: {purpose}", "", resp.model, resp.input_tokens, resp.output_tokens, sw.ms)
        return resp

    def json(self, purpose: str, system: str, user: str, max_tokens: int = 1500):
        """Calls the model and parses JSON; one repair retry if the output is malformed."""
        resp = self.text(purpose, system, user, max_tokens)
        try:
            return extract_json(resp.text)
        except ValueError:
            repair = self.text(purpose + " (repair)", system,
                               user + "\n\nYour previous reply was not valid JSON. Reply with ONLY the JSON.", max_tokens)
            try:
                return extract_json(repair.text)
            except ValueError as e:
                raise LLMUnavailable(f"unparseable JSON from model: {e}") from e
