from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from asnwero_bot.prompts import build_prompt

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    retry_after: float | None = None


class TemporaryProviderError(ProviderError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderAuthError(ProviderError):
    pass


class ProviderBadResponseError(ProviderError):
    pass


class ReplyProvider(Protocol):
    name: str
    model: str

    async def generate(self, source_text: str, tone: str, context: str | None = None) -> list[str]:
        ...


@dataclass
class ProviderStatus:
    disabled: bool = False
    unavailable_until: float = 0


class ProviderRouter:
    def __init__(self, providers: list[ReplyProvider]) -> None:
        self.providers = providers
        self.statuses: dict[str, ProviderStatus] = {provider.name: ProviderStatus() for provider in providers}

    async def generate(self, source_text: str, tone: str, context: str | None = None) -> list[str]:
        now = time.monotonic()
        last_error: Exception | None = None
        for provider in self.providers:
            status = self.statuses[provider.name]
            if status.disabled or status.unavailable_until > now:
                continue
            started = time.monotonic()
            try:
                result = await provider.generate(source_text, tone, context)
                logger.info(
                    "generation_ok provider=%s model=%s duration_ms=%d",
                    provider.name,
                    provider.model,
                    int((time.monotonic() - started) * 1000),
                )
                return validate_variants(result)
            except ProviderAuthError as exc:
                status.disabled = True
                last_error = exc
                logger.warning("provider_disabled provider=%s reason=auth_error", provider.name)
            except (TemporaryProviderError, asyncio.TimeoutError, httpx.HTTPError) as exc:
                retry_after = getattr(exc, "retry_after", None) or 60
                status.unavailable_until = time.monotonic() + retry_after
                last_error = exc
                logger.warning(
                    "provider_temporarily_unavailable provider=%s retry_after=%s",
                    provider.name,
                    retry_after,
                )
            except ProviderBadResponseError as exc:
                last_error = exc
                logger.warning("provider_bad_response provider=%s", provider.name)
        raise TemporaryProviderError("all configured free providers are unavailable") from last_error


def validate_variants(items: list[str]) -> list[str]:
    cleaned = [item.strip() for item in items if isinstance(item, str) and item.strip()]
    unique = list(dict.fromkeys(cleaned))
    if len(unique) != 3:
        raise ProviderBadResponseError("provider returned invalid variants count")
    return unique


def parse_json_variants(value: str) -> list[str]:
    text = strip_markdown_fence(value.strip())
    parsed = parse_variants_payload(text)
    if parsed is not None:
        return parsed

    array_match = re.search(r"\[[\s\S]*\]", text)
    if array_match:
        parsed = parse_variants_payload(array_match.group(0))
        if parsed is not None:
            return parsed
    raise ProviderBadResponseError("provider did not return parseable variants")


def strip_markdown_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_variants_payload(text: str) -> list[str] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list):
        return validate_variants(parsed)
    if isinstance(parsed, dict):
        for key in ("variants", "answers", "replies", "responses", "options"):
            value = parsed.get(key)
            if isinstance(value, list):
                return validate_variants(value)
    return None


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def generate(self, source_text: str, tone: str, context: str | None = None) -> list[str]:
        if not self.api_key:
            raise ProviderAuthError("missing Gemini API key")
        prompt = build_prompt(source_text, tone, context)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": 700, "responseMimeType": "application/json"},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
        handle_status(response)
        data = response.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderBadResponseError("Gemini response shape is invalid") from exc
        return parse_json_variants(text)


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float,
        allow_paid_models: bool,
        site_url: str = "",
        app_name: str = "Asnwero Reply Assistant",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.allow_paid_models = allow_paid_models
        self.site_url = site_url
        self.app_name = app_name

    async def generate(self, source_text: str, tone: str, context: str | None = None) -> list[str]:
        if not self.api_key:
            raise ProviderAuthError("missing OpenRouter API key")
        if not self.allow_paid_models and not (self.model.endswith(":free") or self.model == "openrouter/free"):
            raise ProviderAuthError("paid OpenRouter model is blocked by ALLOW_PAID_MODELS=false")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": self.app_name,
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": build_prompt(source_text, tone, context)}],
            "temperature": 0.8,
            "max_tokens": 700,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        handle_status(response)
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderBadResponseError("OpenRouter response shape is invalid") from exc
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "variants" in parsed:
                return validate_variants(parsed["variants"])
        except json.JSONDecodeError:
            pass
        return parse_json_variants(content)


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def generate(self, source_text: str, tone: str, context: str | None = None) -> list[str]:
        if not self.api_key:
            raise ProviderAuthError("missing Groq API key")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": build_prompt(source_text, tone, context)}],
            "temperature": 0.8,
            "max_completion_tokens": 700,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        handle_status(response)
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderBadResponseError("Groq response shape is invalid") from exc
        return parse_json_variants(content)


class XAIProvider:
    name = "xai"

    def __init__(self, api_key: str, model: str, timeout: float, allow_paid_models: bool) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.allow_paid_models = allow_paid_models

    async def generate(self, source_text: str, tone: str, context: str | None = None) -> list[str]:
        if not self.allow_paid_models:
            raise ProviderAuthError("xAI provider is blocked by ALLOW_PAID_MODELS=false")
        if not self.api_key:
            raise ProviderAuthError("missing xAI API key")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": build_prompt(source_text, tone, context)}],
            "temperature": 0.8,
            "max_tokens": 700,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post("https://api.x.ai/v1/chat/completions", headers=headers, json=payload)
        handle_status(response)
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderBadResponseError("xAI response shape is invalid") from exc
        return parse_json_variants(content)


def handle_status(response: httpx.Response) -> None:
    if response.status_code in {401, 403}:
        raise ProviderAuthError("provider authorization failed")
    if response.status_code == 429 or 500 <= response.status_code <= 599:
        retry_after = response.headers.get("Retry-After")
        retry_seconds = float(retry_after) if retry_after and retry_after.isdigit() else None
        raise TemporaryProviderError(f"provider temporary error {response.status_code}", retry_seconds)
    if response.status_code >= 400:
        raise ProviderBadResponseError(f"provider returned HTTP {response.status_code}")
