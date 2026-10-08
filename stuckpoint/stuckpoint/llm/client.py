"""Gemma 4 client (Person 2). Every model call in the project goes through gemma_json().

- Calls Gemma 4 through the Gemini API (google-genai SDK).
- Asks for JSON; the schema is always written into the prompt, and JSON mode /
  system instructions / minimal thinking are used when the API accepts them for
  the model (each auto-disabled on the first rejection).
- Thinking is set to MINIMAL by default: Gemma 4 otherwise spends thousands of
  "thought" tokens per call (measured: a code review took 146 s vs 6 s).
  GEMMA_THINKING=default restores the model's own behaviour.
- Timeouts are enforced by the HTTP client itself, so a slow call is really
  cancelled and never blocks the calls after it.
- Transient API errors (429 / 5xx / network) are retried once after a short pause.
- Validates against the JSON schema, retries once with the error.
- Caches identical requests, logs every call to logs/llm.jsonl.
- Raises LLMError on failure — callers must catch it and fall back.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any

from .. import config


class LLMError(RuntimeError):
    """Gemma could not produce a valid answer (network, rate limit, bad JSON)."""


_client = None
_client_key: tuple | None = None
_cache: dict[str, dict] = {}
_features = {"json_mode": True, "system_instruction": True,
             "thinking": config.GEMMA_THINKING != "default"}
_TRANSIENT = re.compile(r"\b(429|500|502|503|504)\b|RESOURCE_EXHAUSTED|UNAVAILABLE|INTERNAL|"
                        r"timed out|timeout|connect|RemoteProtocol", re.I)


def _get_client():
    global _client, _client_key
    if not config.GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY is not set (see .env.example)")
    key = (config.GEMINI_API_KEY, config.LLM_TIMEOUT_S)
    if _client is None or _client_key != key:
        from google import genai
        from google.genai import types

        _client = genai.Client(api_key=config.GEMINI_API_KEY,
                               http_options=types.HttpOptions(timeout=int(config.LLM_TIMEOUT_S * 1000)))
        _client_key = key
    return _client


def _log(entry: dict) -> None:
    try:
        os.makedirs(os.path.dirname(config.LLM_LOG), exist_ok=True)
        with open(config.LLM_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply, tolerating ```json fences or chatter around it."""
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON object in reply")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start:end + 1])


def _validate(obj: Any, schema: dict) -> None:
    import jsonschema

    jsonschema.validate(obj, schema)


def _raw_call(prompt: str, system: str, temperature: float, want_json: bool = True) -> str:
    from google.genai import types

    client = _get_client()
    contents = prompt
    kwargs: dict[str, Any] = {"temperature": temperature}
    if system and _features["system_instruction"]:
        kwargs["system_instruction"] = system
    elif system:
        contents = f"{system}\n\n---\n\n{prompt}"
    if want_json and _features["json_mode"]:
        kwargs["response_mime_type"] = "application/json"
    if _features["thinking"]:
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=config.GEMMA_THINKING.upper())

    try:
        resp = client.models.generate_content(
            model=config.GEMMA_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(**kwargs),
        )
    except Exception as e:  # feature not supported for this model -> disable & retry once
        msg = str(e).lower()
        retry = False
        if _features["thinking"] and "thinking" in msg:
            _features["thinking"] = False
            retry = True
        elif _features["json_mode"] and ("json" in msg or "mime" in msg):
            _features["json_mode"] = False
            retry = True
        elif _features["system_instruction"] and ("system" in msg or "developer instruction" in msg):
            _features["system_instruction"] = False
            retry = True
        if retry:
            return _raw_call(prompt, system, temperature, want_json)
        raise
    return resp.text or ""


def _call(prompt: str, system: str, temperature: float, want_json: bool = True) -> str:
    """_raw_call + one retry after a short pause on transient errors (rate limit, 5xx, network)."""
    try:
        return _raw_call(prompt, system, temperature, want_json)
    except LLMError:
        raise
    except Exception as e:
        if not _TRANSIENT.search(f"{type(e).__name__} {e}"):
            raise
        time.sleep(2.0)
        return _raw_call(prompt, system, temperature, want_json)


def gemma_json(prompt: str, schema: dict, *, system: str = "", temperature: float = 0.2,
               retries: int = 1, use_cache: bool = True) -> Any:
    """Ask Gemma 4 for JSON matching `schema`. Returns the parsed, validated object."""
    full_prompt = (
        f"{prompt}\n\nReply with ONLY a JSON value matching this JSON schema "
        f"(no markdown, no commentary):\n{json.dumps(schema)}"
    )
    key = hashlib.sha256(
        json.dumps([config.GEMMA_MODEL, system, full_prompt, temperature]).encode()
    ).hexdigest()
    if use_cache and key in _cache:
        return _cache[key]

    attempt_prompt = full_prompt
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        t0 = time.time()
        reply = ""
        try:
            reply = _call(attempt_prompt, system, temperature)
        except LLMError:
            raise                                   # no API key: retrying won't help
        except Exception as e:                      # API / network error, already retried once
            last_err = e
            _log({"ok": False, "model": config.GEMMA_MODEL, "ms": int((time.time() - t0) * 1000),
                  "error": str(e)[:500], "prompt": attempt_prompt[-4000:]})
            break
        try:
            obj = extract_json(reply)
            _validate(obj, schema)
        except Exception as e:                      # bad JSON / schema mismatch -> tell the model
            last_err = e
            _log({"ok": False, "model": config.GEMMA_MODEL, "ms": int((time.time() - t0) * 1000),
                  "error": str(e)[:500], "prompt": attempt_prompt[-4000:], "reply": reply[:4000]})
            attempt_prompt = (
                f"{full_prompt}\n\nYour previous reply was invalid ({str(e)[:300]}). "
                "Reply again with ONLY valid JSON matching the schema."
            )
            continue
        _log({"ok": True, "model": config.GEMMA_MODEL, "ms": int((time.time() - t0) * 1000),
              "prompt": attempt_prompt[-4000:], "reply": reply[:4000]})
        if use_cache:
            _cache[key] = obj
        return obj
    raise LLMError(str(last_err))


def gemma_text(prompt: str, *, system: str = "", temperature: float = 0.4) -> str:
    """Plain-text call (used only for project-mode code answers)."""
    t0 = time.time()
    try:
        text = _call(prompt, system, temperature, False)
    except LLMError:
        raise
    except Exception as e:
        _log({"ok": False, "model": config.GEMMA_MODEL, "error": str(e)[:500], "prompt": prompt[-4000:]})
        raise LLMError(str(e)) from e
    _log({"ok": True, "model": config.GEMMA_MODEL, "ms": int((time.time() - t0) * 1000),
          "prompt": prompt[-4000:], "reply": text[:4000]})
    return text
