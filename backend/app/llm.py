"""Thin LLM provider layer.

Only this module talks to a model provider. Every call is:
  * JSON-only output, validated by the caller with Pydantic
  * bounded retries
  * metered (tokens + latency) so the trace and eval scorecard can report cost
In offline mode no network call is made; callers use deterministic fallbacks.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from . import config


class LLMUnavailable(RuntimeError):
    pass


@dataclass
class Meter:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(calls=self.calls, prompt_tokens=self.prompt_tokens,
                    completion_tokens=self.completion_tokens, latency_ms=round(self.latency_ms, 1),
                    errors=self.errors[-5:])


_client = None

# Reasoning models (gpt-5*, o1/o3/o4*) reject any temperature other than the
# default of 1. Sampling params are therefore model-dependent, not global: we
# drop temperature for those families and remember any model the API rejects it
# for, so a provider change never costs more than one wasted call.
_NO_TEMPERATURE_PREFIXES = ("gpt-5", "o1", "o3", "o4")
_no_temperature: set[str] = set()


def _supports_temperature(model: str) -> bool:
    name = model.lower()
    if name in _no_temperature:
        return False
    return not name.startswith(_NO_TEMPERATURE_PREFIXES)


def mode() -> str:
    return config.LLM_MODE


def enabled() -> bool:
    return config.LLM_MODE == "openai" and bool(config.OPENAI_API_KEY)


def _get_client():
    global _client
    if not enabled():
        raise LLMUnavailable("LLM disabled (offline mode or no OPENAI_API_KEY)")
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=60, max_retries=2)
    return _client


def complete_json(system: str, user: str, meter: Meter | None = None, temperature: float = 0.0) -> dict:
    """Call the chat model in JSON mode and return the parsed object."""
    client = _get_client()
    model = config.OPENAI_MODEL
    kwargs: dict = dict(
        model=model,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    if _supports_temperature(model):
        kwargs["temperature"] = temperature
    t0 = time.perf_counter()
    try:
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as exc:
            # A model that only accepts the default temperature: drop it and retry once.
            if "temperature" not in kwargs or "temperature" not in str(exc):
                raise
            _no_temperature.add(model.lower())
            kwargs.pop("temperature")
            resp = client.chat.completions.create(**kwargs)
    except Exception as exc:  # network / auth / rate limit
        if meter:
            meter.errors.append(f"{type(exc).__name__}: {exc}"[:200])
        raise
    finally:
        if meter:
            meter.latency_ms += (time.perf_counter() - t0) * 1000
    if meter:
        meter.calls += 1
        usage = getattr(resp, "usage", None)
        if usage:
            meter.prompt_tokens += usage.prompt_tokens or 0
            meter.completion_tokens += usage.completion_tokens or 0
    content = resp.choices[0].message.content or "{}"
    return json.loads(content)


def embed(texts: list[str]) -> list[list[float]]:
    client = _get_client()
    resp = client.embeddings.create(model=config.OPENAI_EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]
