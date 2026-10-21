"""Concrete providers.

anthropic          : Claude API (api.anthropic.com)
anthropic_foundry  : Claude deployed in Microsoft Foundry on Azure. Same Messages
                     API; endpoint https://<resource>.services.ai.azure.com/anthropic/
                     Auth with API key or Entra ID (managed identity).
azure_openai       : GPT models in Azure OpenAI (chat completions).
"""
from app.core.config import Settings
from app.llm.base import LLMProvider, LLMResponse, LLMUnavailable


class NoneProvider(LLMProvider):
    name = "none"

    def complete(self, system, user, max_tokens=1500, temperature=0.0):
        raise LLMUnavailable("LLM_PROVIDER=none - deterministic fallback in use")


class _AnthropicBase(LLMProvider):
    client = None
    model = ""

    def complete(self, system, user, max_tokens=1500, temperature=0.0):
        msg = self.client.messages.create(
            model=self.model, max_tokens=max_tokens, temperature=temperature,
            system=system, messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content)
        return LLMResponse(text=text, model=self.model,
                           input_tokens=msg.usage.input_tokens, output_tokens=msg.usage.output_tokens)


class AnthropicProvider(_AnthropicBase):
    name = "anthropic"

    def __init__(self, s: Settings):
        import anthropic
        if not s.anthropic_api_key:
            raise LLMUnavailable("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.llm_timeout_seconds, max_retries=s.llm_max_retries)
        self.model = s.llm_model


class AnthropicFoundryProvider(_AnthropicBase):
    name = "anthropic_foundry"

    def __init__(self, s: Settings):
        from anthropic import AnthropicFoundry
        if not s.anthropic_foundry_resource:
            raise LLMUnavailable("ANTHROPIC_FOUNDRY_RESOURCE not set")
        kwargs = dict(resource=s.anthropic_foundry_resource, timeout=s.llm_timeout_seconds, max_retries=s.llm_max_retries)
        if s.anthropic_foundry_use_entra:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            kwargs["azure_ad_token_provider"] = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
        else:
            if not s.anthropic_foundry_api_key:
                raise LLMUnavailable("ANTHROPIC_FOUNDRY_API_KEY not set")
            kwargs["api_key"] = s.anthropic_foundry_api_key
        self.client = AnthropicFoundry(**kwargs)
        self.model = s.llm_model  # = your Foundry deployment name


class AzureOpenAIProvider(LLMProvider):
    name = "azure_openai"

    def __init__(self, s: Settings):
        from openai import AzureOpenAI
        if not s.azure_openai_endpoint:
            raise LLMUnavailable("AZURE_OPENAI_ENDPOINT not set")
        if s.azure_openai_api_key:
            self.client = AzureOpenAI(azure_endpoint=s.azure_openai_endpoint, api_key=s.azure_openai_api_key,
                                      api_version=s.azure_openai_api_version, timeout=s.llm_timeout_seconds,
                                      max_retries=s.llm_max_retries)
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            tp = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
            self.client = AzureOpenAI(azure_endpoint=s.azure_openai_endpoint, azure_ad_token_provider=tp,
                                      api_version=s.azure_openai_api_version)
        self.model = s.llm_model  # deployment name

    def complete(self, system, user, max_tokens=1500, temperature=0.0):
        r = self.client.chat.completions.create(
            model=self.model, max_tokens=max_tokens, temperature=temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return LLMResponse(text=r.choices[0].message.content or "", model=self.model,
                           input_tokens=r.usage.prompt_tokens, output_tokens=r.usage.completion_tokens)
