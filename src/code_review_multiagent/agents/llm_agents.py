from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import infer_language
from ..llm_client import generate_json
from ..llm_config import get_llm_config
from ..models import AgentReview, Finding, ReviewFile, Severity


SYSTEM_SUFFIX = """
你必须只从自己的角色维度审查代码。
请输出 JSON，不要输出 markdown，不要包裹 ```。
JSON schema:
{
  "findings": [
    {
      "rule_id": "短规则ID，例如 LLM-SEC-SQL-INJECTION",
      "category": "问题类别",
      "severity": "Critical|High|Medium|Low|Info",
      "file_path": "文件路径",
      "line_start": 1,
      "line_end": 1,
      "evidence": "代码证据或事实依据",
      "impact": "影响",
      "recommendation": "修复建议",
      "confidence": 0.0
    }
  ],
  "notes": ["补充说明"]
}
如果没有发现问题，findings 返回空数组。
""".strip()


@dataclass
class LLMReviewAgent:
    name: str
    role: str
    system_prompt: str

    def review(self, files: list[ReviewFile]) -> AgentReview:
        data = generate_json(
            system=f"{self.system_prompt}\n\n{SYSTEM_SUFFIX}",
            prompt=self._build_prompt(files),
            max_tokens=4000,
        )
        findings: list[Finding] = []
        for raw in data.get("findings", []):
            if not isinstance(raw, dict):
                continue
            finding = _finding_from_llm(self.name, raw)
            finding.fingerprint = finding.stable_fingerprint()
            findings.append(finding)
        notes = [str(item) for item in data.get("notes", [])]
        return AgentReview(agent=self.name, role=self.role, findings=findings, notes=notes)

    def _build_prompt(self, files: list[ReviewFile]) -> str:
        sections = ["请审查下面的项目代码文件。代码来自同一个上传项目，请结合跨文件上下文，但只输出你角色范围内的问题。"]
        for file in files:
            language = infer_language(file.path, file.language)
            numbered = "\n".join(f"{idx:>4}: {line}" for idx, line in enumerate(file.content.splitlines(), start=1))
            sections.append(f"\n文件: {file.path}\n语言: {language}\n```{language}\n{numbered}\n```")
        return "\n".join(sections)


def build_llm_agents(configs: list[object] | None = None) -> list[LLMReviewAgent]:
    config = get_llm_config()
    if not config.api_key or config.api_key == "your_api_key_here":
        return []
    if configs:
        return [
            LLMReviewAgent(
                name=str(getattr(item, "name")),
                role=str(getattr(item, "role")),
                system_prompt=_prompt_with_tools(
                    str(getattr(item, "system_prompt") or getattr(item, "role")),
                    list(getattr(item, "tools", []) or []),
                ),
            )
            for item in configs
            if getattr(item, "kind", "") == "llm" and getattr(item, "enabled", False)
        ]
    return _default_llm_agents()


def _default_llm_agents() -> list[LLMReviewAgent]:
    return [
        LLMReviewAgent(
            name="LLM Security Agent",
            role="使用配置的模型从安全角度审查 SQL 注入、XSS、鉴权、敏感信息泄露、供应链风险。",
            system_prompt="你是 Security Agent，只关注代码安全问题，不评价性能和代码风格。",
        ),
        LLMReviewAgent(
            name="LLM Performance Agent",
            role="使用配置的模型从性能角度审查复杂度、N+1 查询、重复 IO、无界查询、缓存问题。",
            system_prompt="你是 Performance Agent，只关注性能问题，不评价安全和代码风格。",
        ),
        LLMReviewAgent(
            name="LLM Style Agent",
            role="使用配置的模型从可维护性角度审查职责拆分、命名、异常处理、测试友好性。",
            system_prompt="你是 Style Agent，只关注工程质量、可维护性和测试友好性，不评价安全和性能。",
        ),
    ]


def _prompt_with_tools(system_prompt: str, tools: list[str]) -> str:
    if not tools:
        return system_prompt
    return f"{system_prompt}\n\n你可以使用的审查 tools 边界：{', '.join(tools)}。只能围绕这些 tools 对应的能力输出问题。"


def _finding_from_llm(agent_name: str, raw: dict[str, Any]) -> Finding:
    severity_raw = str(raw.get("severity") or "Info")
    try:
        severity = Severity(severity_raw)
    except ValueError:
        severity = Severity.INFO
    return Finding(
        agent=agent_name,
        rule_id=str(raw.get("rule_id") or f"LLM-{agent_name.upper().replace(' ', '-')}")[:80],
        category=str(raw.get("category") or "LLM Finding")[:120],
        severity=severity,
        file_path=str(raw.get("file_path") or "unknown"),
        line_start=_optional_int(raw.get("line_start")),
        line_end=_optional_int(raw.get("line_end")),
        evidence=str(raw.get("evidence") or "模型发现的问题"),
        impact=str(raw.get("impact") or "需要人工确认影响"),
        recommendation=str(raw.get("recommendation") or "请结合上下文修复"),
        confidence=float(raw.get("confidence") or 0.7),
    )


def _optional_int(value: Any) -> int | None:
    if value in {None, "", 0}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
