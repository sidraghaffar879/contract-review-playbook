"""Provider-agnostic LLM client (Anthropic / OpenAI / Bedrock) with an offline fake for tests and CI.
Configure with CR_LLM_PROVIDER=fake|anthropic|openai|bedrock and CR_LLM_MODEL."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Protocol


class LLM(Protocol):
    def complete(self, system: str, user: str, *, max_tokens: int = 1500) -> str: ...


def parse_json(text: str, default: Any = None) -> Any:
    m = re.search(r"[\[{].*[\]}]", text, flags=re.S)
    try:
        return json.loads(m.group() if m else text)
    except Exception:
        return default


class FakeLLM:
    def __init__(self, responder: Callable[[str, str], str]):
        self._r = responder

    def complete(self, system: str, user: str, *, max_tokens: int = 1500) -> str:
        return self._r(system, user)


class AnthropicLLM:
    def __init__(self, model: str):
        import anthropic

        self._c, self._m = anthropic.Anthropic(), model

    def complete(self, system, user, *, max_tokens=1500):
        r = self._c.messages.create(model=self._m, max_tokens=max_tokens, temperature=0, system=system,
                                    messages=[{"role": "user", "content": user}])
        return r.content[0].text


class OpenAILLM:
    def __init__(self, model: str):
        from openai import OpenAI

        self._c, self._m = OpenAI(), model

    def complete(self, system, user, *, max_tokens=1500):
        r = self._c.chat.completions.create(model=self._m, max_tokens=max_tokens, temperature=0,
                                            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.choices[0].message.content or ""


class BedrockLLM:
    def __init__(self, model: str):
        import boto3

        self._c, self._m = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1")), model

    def complete(self, system, user, *, max_tokens=1500):
        r = self._c.converse(modelId=self._m, system=[{"text": system}], messages=[{"role": "user", "content": [{"text": user}]}],
                             inferenceConfig={"maxTokens": max_tokens, "temperature": 0})
        return r["output"]["message"]["content"][0]["text"]


def get_llm(fake_responder: Callable[[str, str], str]) -> LLM:
    p = os.getenv("CR_LLM_PROVIDER", "fake").lower()
    m = os.getenv("CR_LLM_MODEL", "claude-sonnet-4-6")
    if p == "anthropic":
        return AnthropicLLM(m)
    if p == "openai":
        return OpenAILLM(m)
    if p == "bedrock":
        return BedrockLLM(m)
    return FakeLLM(fake_responder)
