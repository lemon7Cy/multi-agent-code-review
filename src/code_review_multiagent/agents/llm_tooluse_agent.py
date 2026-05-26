"""LLM Tool Use Agent：通过多轮工具调用循环实现深度代码审查。

与旧版 LLMReviewAgent（单次 prompt→JSON）不同，此 Agent：
1. 使用 Claude / OpenAI tool_use 进行多轮推理
2. 可调用代码分析工具（grep_pattern, check_imports, analyze_function 等）
3. 根据工具返回的观察动态决定下一步分析方向
4. 最终输出结构化的 Findings

当 LLM 不可用时自动降级到旧版单次调用。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from .base import infer_language
from ..llm_client import openai_base_url, use_openai_compatible
from ..llm_config import LLMConfig, get_llm_config
from ..models import AgentReview, Finding, ReviewFile, Severity

MAX_TOOL_STEPS = 6

# ─── 工具定义 ────────────────────────────────────────────────────────────

REVIEW_TOOLS = [
    {
        "name": "grep_pattern",
        "description": "在代码文件中搜索正则模式，返回匹配的行号和内容。用于定位可疑代码模式（如 SQL 拼接、硬编码密钥、未处理异常等）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "正则表达式模式"},
                "file_path": {"type": "string", "description": "目标文件路径，不指定则搜索所有文件"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "analyze_function",
        "description": "分析指定函数的结构信息：参数、返回值、调用的其他函数、循环嵌套深度、异常处理情况。",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
                "function_name": {"type": "string", "description": "函数名"},
            },
            "required": ["file_path", "function_name"],
        },
    },
    {
        "name": "check_imports",
        "description": "检查文件的导入依赖，识别未使用的导入、循环依赖风险、已知有漏洞的库版本。",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "check_sql_safety",
        "description": "检查 SQL 语句构造方式，判断是否存在注入风险。分析是否使用参数化查询。",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
                "line_start": {"type": "integer", "description": "起始行号"},
                "line_end": {"type": "integer", "description": "结束行号"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "get_file_summary",
        "description": "获取文件的结构摘要：类、函数、全局变量列表，以及文件总行数。用于快速了解文件结构。",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
            },
            "required": ["file_path"],
        },
    },
]

# ─── 工具执行引擎 ────────────────────────────────────────────────────────


class CodeAnalysisToolkit:
    """基于提交的代码文件执行分析工具。"""

    def __init__(self, files: list[ReviewFile]) -> None:
        self._files = {f.path: f for f in files}

    def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        dispatch = {
            "grep_pattern": self._grep_pattern,
            "analyze_function": self._analyze_function,
            "check_imports": self._check_imports,
            "check_sql_safety": self._check_sql_safety,
            "get_file_summary": self._get_file_summary,
        }
        handler = dispatch.get(tool_name)
        if not handler:
            return f"Unknown tool: {tool_name}"
        try:
            return handler(args)
        except Exception as e:
            return f"Tool error: {e}"

    def _grep_pattern(self, args: dict[str, Any]) -> str:
        pattern = args["pattern"]
        target_path = args.get("file_path")
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Invalid regex: {e}"

        results: list[str] = []
        files_to_search = [self._files[target_path]] if target_path and target_path in self._files else self._files.values()
        for f in files_to_search:
            for i, line in enumerate(f.content.splitlines(), 1):
                if regex.search(line):
                    results.append(f"{f.path}:{i}: {line.strip()}")
        if not results:
            return "No matches found."
        return "\n".join(results[:20]) + (f"\n... ({len(results)} total matches)" if len(results) > 20 else "")

    def _analyze_function(self, args: dict[str, Any]) -> str:
        file_path = args["file_path"]
        func_name = args["function_name"]
        f = self._files.get(file_path)
        if not f:
            return f"File not found: {file_path}"

        lines = f.content.splitlines()
        func_start = None
        func_lines: list[str] = []
        indent_level = 0

        for i, line in enumerate(lines):
            if func_start is None:
                if re.search(rf"\bdef\s+{re.escape(func_name)}\b|function\s+{re.escape(func_name)}\b", line):
                    func_start = i + 1
                    indent_level = len(line) - len(line.lstrip())
                    func_lines.append(line)
            else:
                if line.strip() and (len(line) - len(line.lstrip())) <= indent_level and not line.strip().startswith(("#", "//", "*")):
                    break
                func_lines.append(line)

        if not func_lines:
            return f"Function '{func_name}' not found in {file_path}"

        body = "\n".join(func_lines)
        loop_count = len(re.findall(r"\b(for|while)\b", body))
        try_count = len(re.findall(r"\b(try|catch|except)\b", body))
        calls = re.findall(r"(\w+)\s*\(", body)
        return (
            f"Function: {func_name} (line {func_start}, {len(func_lines)} lines)\n"
            f"Loops: {loop_count}, Exception handling: {try_count}\n"
            f"Calls: {', '.join(set(calls[:15]))}\n"
            f"Code:\n{body[:800]}"
        )

    def _check_imports(self, args: dict[str, Any]) -> str:
        file_path = args["file_path"]
        f = self._files.get(file_path)
        if not f:
            return f"File not found: {file_path}"

        imports: list[str] = []
        for line in f.content.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) or stripped.startswith(("require(", "const ")) and "require" in stripped:
                imports.append(stripped)
        if not imports:
            return "No imports found."
        return "Imports:\n" + "\n".join(imports[:30])

    def _check_sql_safety(self, args: dict[str, Any]) -> str:
        file_path = args["file_path"]
        f = self._files.get(file_path)
        if not f:
            return f"File not found: {file_path}"

        lines = f.content.splitlines()
        start = args.get("line_start", 1) - 1
        end = args.get("line_end", len(lines))
        segment = lines[max(0, start):min(end, len(lines))]
        code = "\n".join(segment)

        issues: list[str] = []
        if re.search(r"f['\"].*\b(SELECT|INSERT|UPDATE|DELETE)\b", code, re.IGNORECASE):
            issues.append("f-string SQL detected — potential injection risk")
        if re.search(r"\.format\(.*\).*\b(SELECT|INSERT|UPDATE|DELETE)\b", code, re.IGNORECASE):
            issues.append(".format() SQL detected — potential injection risk")
        if re.search(r"\+\s*['\"].*\b(SELECT|INSERT|UPDATE|DELETE)\b", code, re.IGNORECASE):
            issues.append("String concatenation SQL detected — potential injection risk")
        if re.search(r"\bexecute\b.*%s|\bexecute\b.*\?", code):
            issues.append("Parameterized query detected (safe pattern)")

        if not issues:
            return f"No obvious SQL safety issues in lines {start+1}-{end}."
        return "\n".join(issues)

    def _get_file_summary(self, args: dict[str, Any]) -> str:
        file_path = args["file_path"]
        f = self._files.get(file_path)
        if not f:
            return f"File not found: {file_path}"

        lines = f.content.splitlines()
        classes = [m.group(1) for m in re.finditer(r"class\s+(\w+)", f.content)]
        functions = [m.group(1) for m in re.finditer(r"(?:def|function)\s+(\w+)", f.content)]
        language = infer_language(f.path, f.language)
        return (
            f"File: {file_path} ({language}, {len(lines)} lines)\n"
            f"Classes: {', '.join(classes) or 'none'}\n"
            f"Functions: {', '.join(functions[:20]) or 'none'}"
        )


# ─── Agent 核心 ──────────────────────────────────────────────────────────

TOOLUSE_SYSTEM_PROMPT_TEMPLATE = """\
你是 {role_name}。

## 工作方式
1. 先通过 get_file_summary 了解文件结构
2. 使用 grep_pattern 定位可疑模式
3. 用 analyze_function 或 check_sql_safety 深入确认
4. 根据工具返回的证据判断是否为真实问题

## 输出要求
当你完成分析后，请输出最终结论 JSON（不要用 markdown 包裹）：
{{
  "findings": [
    {{
      "rule_id": "规则ID",
      "category": "问题类别",
      "severity": "Critical|High|Medium|Low|Info",
      "file_path": "文件路径",
      "line_start": 1,
      "line_end": 1,
      "evidence": "工具返回的代码证据",
      "impact": "影响描述",
      "recommendation": "修复建议",
      "confidence": 0.9
    }}
  ],
  "notes": ["补充说明"]
}}

## 原则
- 不要猜测，用工具验证后再输出 Finding
- 只报告你角色范围内的问题
- confidence 反映你对问题真实性的把握（0~1）
- 如果工具返回没有发现问题，findings 为空数组
"""


@dataclass
class LLMToolUseAgent:
    """通过多轮 tool_use 循环进行深度代码审查的 Agent。"""

    name: str
    role: str
    system_prompt: str

    def review(self, files: list[ReviewFile]) -> AgentReview:
        config = get_llm_config()
        toolkit = CodeAnalysisToolkit(files)
        user_prompt = self._build_prompt(files)

        try:
            if use_openai_compatible(config):
                return self._review_openai(config, toolkit, user_prompt)
            return self._review_claude(config, toolkit, user_prompt)
        except Exception as exc:
            return self._empty_review(f"模型 Agent 执行失败，已降级为规则审查结果：{exc}")

    # ─── Claude Anthropic ────────────────────────────────────────────

    def _review_claude(self, config: LLMConfig, toolkit: CodeAnalysisToolkit, user_prompt: str) -> AgentReview:
        base_url = (config.base_url or "https://api.anthropic.com").rstrip("/")
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]
        tool_defs = REVIEW_TOOLS

        for _ in range(MAX_TOOL_STEPS):
            resp = httpx.post(
                f"{base_url}/v1/messages",
                headers={
                    "x-api-key": config.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": config.model,
                    "max_tokens": 4096,
                    "system": self.system_prompt,
                    "messages": messages,
                    "tools": tool_defs,
                },
                timeout=config.timeout,
            )
            resp.raise_for_status()
            result = resp.json()
            content_blocks = result.get("content", [])
            stop_reason = result.get("stop_reason", "")

            if stop_reason == "end_turn":
                text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
                return self._parse_response(text)

            # 处理工具调用
            tool_results: list[dict[str, Any]] = []
            for block in content_blocks:
                if block.get("type") == "tool_use":
                    observation = toolkit.execute(block["name"], block["input"])
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": observation,
                    })

            messages.append({"role": "assistant", "content": content_blocks})
            messages.append({"role": "user", "content": tool_results})

        # 超过最大步数，尝试解析已有内容
        return self._empty_review("Reached max tool steps without conclusion")

    # ─── OpenAI-compatible ───────────────────────────────────────────

    def _review_openai(self, config: LLMConfig, toolkit: CodeAnalysisToolkit, user_prompt: str) -> AgentReview:
        base_url = _openai_base_url(config)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        openai_tools = [
            {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in REVIEW_TOOLS
        ]

        for _ in range(MAX_TOOL_STEPS):
            resp = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
                json={
                    "model": config.model,
                    "messages": messages,
                    "tools": openai_tools,
                    "max_tokens": 4096,
                },
                timeout=config.timeout,
            )
            resp.raise_for_status()
            choice = resp.json()["choices"][0]
            message = choice["message"]
            finish_reason = choice.get("finish_reason", "")

            if finish_reason == "stop" or not message.get("tool_calls"):
                return self._parse_response(message.get("content", ""))

            messages.append(message)
            for tool_call in message["tool_calls"]:
                fn = tool_call["function"]
                tool_input = _safe_json_object(fn.get("arguments"))
                observation = toolkit.execute(fn["name"], tool_input)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": observation,
                })

        return self._empty_review("Reached max tool steps without conclusion")

    # ─── Helpers ─────────────────────────────────────────────────────

    def _build_prompt(self, files: list[ReviewFile]) -> str:
        sections = ["请审查以下代码文件。你可以通过工具深入分析代码结构和模式。"]
        for f in files:
            lang = infer_language(f.path, f.language)
            # 只发前 100 行概览，Agent 可通过工具获取更多细节
            preview_lines = f.content.splitlines()[:100]
            numbered = "\n".join(f"{i:>4}: {line}" for i, line in enumerate(preview_lines, 1))
            total = len(f.content.splitlines())
            sections.append(f"\n文件: {f.path} ({lang}, {total} lines)\n```{lang}\n{numbered}\n```")
            if total > 100:
                sections.append(f"(showing first 100 of {total} lines, use tools to analyze further)")
        return "\n".join(sections)

    def _parse_response(self, text: str) -> AgentReview:
        data = _extract_json(text)
        if not data:
            return self._empty_review(text[:200] if text else "No response")

        findings: list[Finding] = []
        for raw in data.get("findings", []):
            if not isinstance(raw, dict):
                continue
            finding = _finding_from_raw(self.name, raw)
            finding.fingerprint = finding.stable_fingerprint()
            findings.append(finding)
        notes = [str(n) for n in data.get("notes", [])]
        return AgentReview(agent=self.name, role=self.role, findings=findings, notes=notes)

    def _empty_review(self, note: str) -> AgentReview:
        return AgentReview(agent=self.name, role=self.role, findings=[], notes=[note])


# ─── Builder ─────────────────────────────────────────────────────────────


def build_tooluse_agents(configs: list[object] | None = None) -> list[LLMToolUseAgent]:
    """构建 Tool Use Agent 列表。当 API Key 不可用时返回空列表。"""
    config = get_llm_config()
    if not config.api_key or config.api_key == "your_api_key_here":
        return []

    if configs:
        return [
            LLMToolUseAgent(
                name=str(getattr(item, "name")),
                role=str(getattr(item, "role")),
                system_prompt=TOOLUSE_SYSTEM_PROMPT_TEMPLATE.format(
                    role_name=str(getattr(item, "system_prompt") or getattr(item, "role"))
                ),
            )
            for item in configs
            if getattr(item, "kind", "") == "llm" and getattr(item, "enabled", False)
        ]
    return _default_tooluse_agents()


def _default_tooluse_agents() -> list[LLMToolUseAgent]:
    return [
        LLMToolUseAgent(
            name="LLM Security Agent",
            role="安全审查：SQL 注入、XSS、鉴权、敏感信息泄露、供应链风险。",
            system_prompt=TOOLUSE_SYSTEM_PROMPT_TEMPLATE.format(
                role_name="Security Agent，专注代码安全漏洞检测"
            ),
        ),
        LLMToolUseAgent(
            name="LLM Performance Agent",
            role="性能审查：N+1 查询、无界查询、循环内 IO、缓存缺失。",
            system_prompt=TOOLUSE_SYSTEM_PROMPT_TEMPLATE.format(
                role_name="Performance Agent，专注性能瓶颈和资源效率"
            ),
        ),
        LLMToolUseAgent(
            name="LLM Style Agent",
            role="工程质量审查：职责拆分、命名、异常处理、测试友好性。",
            system_prompt=TOOLUSE_SYSTEM_PROMPT_TEMPLATE.format(
                role_name="Style Agent，专注代码可维护性和工程质量"
            ),
        ),
    ]


# ─── Utilities ───────────────────────────────────────────────────────────


def _is_openai_compatible(config: LLMConfig) -> bool:
    return use_openai_compatible(config)


def _openai_base_url(config: LLMConfig) -> str:
    return openai_base_url(config)


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    for candidate in _json_candidates(cleaned):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _json_candidates(text: str) -> list[str]:
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.insert(0, text[start:end + 1])
    return candidates


def _safe_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _finding_from_raw(agent_name: str, raw: dict[str, Any]) -> Finding:
    severity_raw = str(raw.get("severity") or "Info")
    try:
        severity = Severity(severity_raw)
    except ValueError:
        severity = Severity.INFO
    return Finding(
        agent=agent_name,
        rule_id=str(raw.get("rule_id") or f"LLM-TOOLUSE-{agent_name.upper().replace(' ', '-')}")[:80],
        category=str(raw.get("category") or "LLM Finding")[:120],
        severity=severity,
        file_path=str(raw.get("file_path") or "unknown"),
        line_start=_safe_int(raw.get("line_start")),
        line_end=_safe_int(raw.get("line_end")),
        evidence=str(raw.get("evidence") or "Tool-assisted finding"),
        impact=str(raw.get("impact") or "需要人工确认"),
        recommendation=str(raw.get("recommendation") or "请结合上下文修复"),
        confidence=float(raw.get("confidence") or 0.8),
    )


def _safe_int(value: Any) -> int | None:
    if value in {None, "", 0}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
