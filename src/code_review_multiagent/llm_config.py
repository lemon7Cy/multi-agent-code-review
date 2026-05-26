from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Provider = Literal["claude", "deepseek", "newapi"]

CONFIG_PATH = Path(__file__).with_name("llm_runtime_config.json")


class LLMConfig(BaseModel):
    provider: Provider = "claude"
    api_key: str = ""
    base_url: str = ""
    model: str = "claude-opus-4-6-thinking"
    timeout: float = Field(default=300.0, ge=1)


class LLMConfigPublic(BaseModel):
    provider: Provider
    base_url: str
    model: str
    timeout: float
    api_key_set: bool


class LLMConfigUpdate(BaseModel):
    provider: Provider
    api_key: str | None = None
    base_url: str = ""
    model: str
    timeout: float = Field(default=300.0, ge=1)


class LLMModelsRequest(BaseModel):
    provider: Provider
    api_key: str | None = None
    base_url: str = ""
    model: str = ""
    timeout: float = Field(default=300.0, ge=1)


def _env_default() -> LLMConfig:
    provider = os.getenv("LLM_PROVIDER", "claude").lower()
    if provider not in {"claude", "deepseek", "newapi"}:
        provider = "claude"

    if provider == "deepseek":
        return LLMConfig(
            provider="deepseek",
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            timeout=float(os.getenv("LLM_TIMEOUT", "300")),
        )

    if provider == "newapi":
        return LLMConfig(
            provider="newapi",
            api_key=os.getenv("NEWAPI_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            base_url=os.getenv("NEWAPI_BASE_URL", ""),
            model=os.getenv("NEWAPI_MODEL", os.getenv("OPENAI_MODEL", "codex-mini-latest")),
            timeout=float(os.getenv("LLM_TIMEOUT", "300")),
        )

    return LLMConfig(
        provider="claude",
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        base_url=os.getenv("ANTHROPIC_BASE_URL", ""),
        model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-6-thinking"),
        timeout=float(os.getenv("LLM_TIMEOUT", "300")),
    )


def get_llm_config() -> LLMConfig:
    if not CONFIG_PATH.exists():
        return _env_default()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return LLMConfig(**data)
    except Exception:
        return _env_default()


def public_config(config: LLMConfig | None = None) -> LLMConfigPublic:
    cfg = config or get_llm_config()
    return LLMConfigPublic(
        provider=cfg.provider,
        base_url=cfg.base_url,
        model=cfg.model,
        timeout=cfg.timeout,
        api_key_set=bool(cfg.api_key),
    )


def save_llm_config(update: LLMConfigUpdate) -> LLMConfig:
    current = get_llm_config()
    api_key = current.api_key if update.api_key is None else update.api_key.strip()
    config = LLMConfig(
        provider=update.provider,
        api_key=api_key,
        base_url=update.base_url.strip(),
        model=update.model.strip(),
        timeout=update.timeout,
    )
    if config.provider == "deepseek" and not config.base_url:
        config.base_url = "https://api.deepseek.com"
    if config.provider == "claude" and not config.model:
        config.model = "claude-opus-4-6-thinking"
    if config.provider == "deepseek" and not config.model:
        config.model = "deepseek-v4-pro"
    if config.provider == "newapi" and not config.model:
        config.model = "codex-mini-latest"

    CONFIG_PATH.write_text(json.dumps(config.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return config
