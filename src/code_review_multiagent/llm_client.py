from __future__ import annotations

import json
from typing import Any

import anthropic
import httpx

from .llm_config import LLMConfig, get_llm_config


def openai_base_url(config: LLMConfig) -> str:
    base_url = (config.base_url or "").rstrip("/")
    if config.provider in {"deepseek", "newapi"} and base_url and not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    return base_url


def use_openai_compatible(config: LLMConfig) -> bool:
    if config.provider in {"deepseek", "newapi"}:
        return True
    # provider=claude 始终按 Anthropic Messages API 调用：
    # official base_url 为空；Claude-compatible proxy 也应暴露 /v1/messages。
    # 如果是 OpenAI-compatible 中转站，请在前端选择 newapi。
    return False


async def list_models(config: LLMConfig) -> list[str]:
    if not config.api_key:
        raise RuntimeError("LLM API key is not configured")

    if not use_openai_compatible(config):
        client = anthropic.AsyncAnthropic(
            api_key=config.api_key,
            base_url=config.base_url or None,
            timeout=config.timeout,
        )
        models = await client.models.list()
        return sorted(model.id for model in models.data if getattr(model, "id", None))

    base_url = openai_base_url(config)
    if not base_url:
        raise RuntimeError("OpenAI-compatible base_url is not configured")

    candidate_urls = [f"{base_url}/models"]
    raw_base = (config.base_url or "").rstrip("/")
    if raw_base and raw_base != base_url:
        candidate_urls.append(f"{raw_base}/models")

    last_error = ""
    async with httpx.AsyncClient(timeout=config.timeout) as client:
        for url in candidate_urls:
            try:
                response = await client.get(url, headers={"Authorization": f"Bearer {config.api_key}"})
                response.raise_for_status()
                payload = response.json()
                raw_models = payload.get("data", payload) if isinstance(payload, dict) else payload
                model_ids: list[str] = []
                if isinstance(raw_models, list):
                    for item in raw_models:
                        if isinstance(item, str):
                            model_ids.append(item)
                        elif isinstance(item, dict):
                            model_id = item.get("id") or item.get("model") or item.get("name")
                            if model_id:
                                model_ids.append(str(model_id))
                return sorted(set(model_ids))
            except Exception as e:
                preview = ""
                try:
                    preview = response.text[:200].replace("\n", " ")  # type: ignore[name-defined]
                except Exception:
                    pass
                last_error = f"{url}: {e}; response={preview}"
    raise RuntimeError(last_error or "failed to fetch models")


async def test_model(config: LLMConfig) -> str:
    if not config.api_key:
        raise RuntimeError("LLM API key is not configured")
    if not config.model:
        raise RuntimeError("LLM model is not configured")

    if not use_openai_compatible(config):
        client = anthropic.AsyncAnthropic(
            api_key=config.api_key,
            base_url=config.base_url or None,
            timeout=config.timeout,
        )
        response = await client.messages.create(
            model=config.model,
            max_tokens=16,
            temperature=0,
            messages=[{"role": "user", "content": "Reply with OK only."}],
        )
        return "".join(
            getattr(block, "text", "") for block in response.content if getattr(block, "type", "") == "text"
        ).strip()

    response = await _openai_chat(config, [{"role": "user", "content": "Reply with OK only."}], max_tokens=16)
    return response.strip()


def generate_json(system: str, prompt: str, max_tokens: int = 4000) -> dict[str, Any]:
    config = get_llm_config()
    if not config.api_key:
        raise RuntimeError("LLM API key is not configured")
    if not config.model:
        raise RuntimeError("LLM model is not configured")

    if not use_openai_compatible(config):
        client = anthropic.Anthropic(api_key=config.api_key, base_url=config.base_url or None, timeout=config.timeout)
        response = client.messages.create(
            model=config.model,
            max_tokens=max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "\n".join(block.text for block in response.content if block.type == "text")
        return load_json_object(text)

    with httpx.Client(timeout=config.timeout) as client:
        response = client.post(
            f"{openai_base_url(config)}/chat/completions",
            headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
            json={
                "model": config.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        payload = response.json()
        text = payload["choices"][0]["message"].get("content") or "{}"
        return load_json_object(text)


async def _openai_chat(config: LLMConfig, messages: list[dict[str, str]], max_tokens: int = 16) -> str:
    async with httpx.AsyncClient(timeout=config.timeout) as client:
        response = await client.post(
            f"{openai_base_url(config)}/chat/completions",
            headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
            json={"model": config.model, "messages": messages, "temperature": 0, "max_tokens": max_tokens},
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"].get("content") or ""


def load_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM did not return valid JSON: {text[:240]}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"LLM JSON response must be an object: {type(data).__name__}")
    return data
