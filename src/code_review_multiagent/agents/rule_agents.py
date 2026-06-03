from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from ..models import AgentReview, Finding, ReviewFile, Severity
from ..review_context import is_test_path
from .base import RuleContext, find_line, infer_language

Rule = Callable[[str, RuleContext], Finding | None]
ToolRule = tuple[str, Rule]


SECRET_RE = re.compile(
    r"(?i)("
    r"sk-[a-z0-9_-]{8,}|"
    r"['\"]?(api[_-]?key|secret|token|debug_token)['\"]?\s*[:=]\s*['\"][^'\"]{6,}"
    r")"
)
SQL_CONCAT_RE = re.compile(r"SELECT\s+.+(\+\s*\w+|\{\w+\}|%s|format\()", re.IGNORECASE)
REQUEST_ID_RE = re.compile(r"request\.(args|GET|query|params).*id|req\.query\.id|params\[:id\]", re.IGNORECASE)
DB_CALL_RE = re.compile(r"(db\.execute|cursor\.execute|\.query\(|findOne\(|find_many|SELECT\s+)", re.IGNORECASE)
LOOP_RE = re.compile(r"^\s*(for\s+.+\s+in\s+.+:|for\s*\(|while\s+)")


def security_sql_injection(agent: str, ctx: RuleContext) -> Finding | None:
    for idx, line in enumerate(ctx.lines, start=1):
        if SQL_CONCAT_RE.search(line) or ('f"SELECT' in line and "{" in line):
            return Finding(
                agent=agent,
                rule_id="SEC-SQL-INJECTION",
                category="SQL 注入风险",
                severity=Severity.HIGH,
                file_path=ctx.file.path,
                line_start=idx,
                evidence=line.strip(),
                impact="攻击者可通过可控输入拼接 SQL，读取或篡改数据库数据。",
                recommendation="改为参数化查询；批量查询时也要使用绑定参数，不要拼接 IN 条件。",
                confidence=0.92,
            )
    return None


def security_hardcoded_secret(agent: str, ctx: RuleContext) -> Finding | None:
    for idx, line in enumerate(ctx.lines, start=1):
        if SECRET_RE.search(line):
            return Finding(
                agent=agent,
                rule_id="SEC-HARDCODED-SECRET",
                category="敏感信息泄露",
                severity=Severity.MEDIUM,
                file_path=ctx.file.path,
                line_start=idx,
                evidence=line.strip(),
                impact="密钥或调试 token 进入代码仓库/响应体后，可能造成凭证泄露。",
                recommendation="删除硬编码敏感值；使用环境变量、密钥管理服务，并避免在 API 响应中返回。",
                confidence=0.88,
            )
    return None


def security_missing_authorization(agent: str, ctx: RuleContext) -> Finding | None:
    content = ctx.file.content
    if not REQUEST_ID_RE.search(content):
        return None
    auth_markers = ["current_user", "is_authenticated", "permission", "authorize", "authz", "owner_id"]
    if any(marker in content for marker in auth_markers):
        return None
    return Finding(
        agent=agent,
        rule_id="SEC-MISSING-AUTHZ",
        category="越权访问风险",
        severity=Severity.MEDIUM,
        file_path=ctx.file.path,
        line_start=find_line(ctx.lines, "id"),
        evidence="从 request 中读取 id 后直接查询资源，未发现权限/归属校验。",
        impact="用户可能通过修改 id 越权访问其他用户资料。",
        recommendation="查询前校验当前登录用户是否有权访问目标资源；必要时按 current_user 约束查询条件。",
        confidence=0.76,
    )


def performance_n_plus_one(agent: str, ctx: RuleContext) -> Finding | None:
    loop_line: int | None = None
    for idx, line in enumerate(ctx.lines, start=1):
        if LOOP_RE.search(line):
            loop_line = idx
        if loop_line and idx > loop_line and idx <= loop_line + 8 and DB_CALL_RE.search(line):
            return Finding(
                agent=agent,
                rule_id="PERF-N-PLUS-ONE",
                category="N+1 查询",
                severity=Severity.MEDIUM,
                file_path=ctx.file.path,
                line_start=idx,
                evidence=line.strip(),
                impact="集合数量增大时，数据库往返次数线性增加，接口延迟和数据库压力都会上升。",
                recommendation="先收集 id，再使用批量查询；同时保留索引并控制返回字段。",
                confidence=0.9,
            )
    return None


def performance_unbounded_result(agent: str, ctx: RuleContext) -> Finding | None:
    content = ctx.file.content.lower()
    if "select *" in content and "limit" not in content and "fetchall" in content:
        return Finding(
            agent=agent,
            rule_id="PERF-UNBOUNDED-QUERY",
            category="无界查询",
            severity=Severity.MEDIUM,
            file_path=ctx.file.path,
            line_start=find_line(ctx.lines, "SELECT *"),
            evidence="查询没有 limit/pagination，且可能一次性 fetchall。",
            impact="数据量增长后会造成响应慢、内存占用高。",
            recommendation="增加分页、limit 和必要字段选择，避免无界结果集。",
            confidence=0.72,
        )
    return None


def style_too_many_responsibilities(agent: str, ctx: RuleContext) -> Finding | None:
    content = ctx.file.content
    has_request = "request" in content or "req." in content
    has_db = "db." in content or ".query(" in content or "execute(" in content
    has_response = "return {" in content or "jsonify" in content or "Response" in content
    if has_request and has_db and has_response:
        return Finding(
            agent=agent,
            rule_id="STYLE-MIXED-RESPONSIBILITY",
            category="可维护性问题",
            severity=Severity.LOW,
            file_path=ctx.file.path,
            line_start=1,
            evidence="同一函数同时处理请求解析、数据访问和响应组装。",
            impact="职责耦合后，安全修复、性能优化和接口变更容易互相影响，测试也更困难。",
            recommendation="拆成 controller / service / repository / serializer，并分别编写单元测试。",
            confidence=0.84,
        )
    return None


def style_missing_error_handling(agent: str, ctx: RuleContext) -> Finding | None:
    content = ctx.file.content
    if ("fetchone()" in content or "findOne" in content) and not any(
        x in content for x in ["if not", "try:", "except", "catch"]
    ):
        return Finding(
            agent=agent,
            rule_id="STYLE-MISSING-ERROR-HANDLING",
            category="异常处理缺失",
            severity=Severity.LOW,
            file_path=ctx.file.path,
            line_start=find_line(ctx.lines, "fetchone()") or find_line(ctx.lines, "findOne"),
            evidence="单条查询结果可能为空，但后续没有显式空值处理。",
            impact="资源不存在时可能触发 500，而不是返回可理解的 404/业务错误。",
            recommendation="显式处理 not found 分支，并为异常路径补充测试。",
            confidence=0.78,
        )
    return None


PRODUCTION_CODE_RE = re.compile(r"\b(def|class|function|export|public|private|func)\b")


def _module_stem(path: str) -> str:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    if "." in name:
        name = name.rsplit(".", 1)[0]
    if name.startswith("test_"):
        name = name[5:]
    if name.endswith("_test"):
        name = name[:-5]
    return name.lower().replace("-", "_")


@dataclass
class TestCoverageAgent:
    name: str = "Test Coverage Agent"
    role: str = "关注生产代码变更是否具备相邻或命名匹配的测试覆盖。"

    def review(self, files: list[ReviewFile]) -> AgentReview:
        test_stems = {_module_stem(file.path) for file in files if is_test_path(file.path)}
        findings: list[Finding] = []
        notes: list[str] = []

        for file in files:
            if is_test_path(file.path):
                continue
            language = infer_language(file.path, file.language)
            if language not in {"python", "javascript", "typescript", "java", "go"}:
                continue
            if not PRODUCTION_CODE_RE.search(file.content):
                continue
            module = _module_stem(file.path)
            if module in test_stems:
                continue
            lines = file.content.splitlines()
            finding = Finding(
                agent=self.name,
                rule_id="TEST-MISSING-COVERAGE",
                category="测试覆盖缺失",
                severity=Severity.MEDIUM,
                file_path=file.path,
                line_start=find_line(lines, "def ") or find_line(lines, "function") or 1,
                evidence=f"生产代码 `{file.path}` 有逻辑变更，但未发现命名匹配的测试文件。",
                impact="缺少回归测试会降低重构和发布信心，易遗漏边界条件或异常路径。",
                recommendation="为本次变更补充对应单元/集成测试；建议使用 test_模块名 或 模块名.test/spec 命名。",
                confidence=0.74,
            )
            finding.fingerprint = finding.stable_fingerprint()
            findings.append(finding)

        if not findings and test_stems:
            notes.append("已发现与生产代码命名匹配或相关的测试覆盖。")
        return AgentReview(agent=self.name, role=self.role, findings=findings, notes=notes)


@dataclass
class RuleBasedAgent:
    name: str
    role: str
    rules: list[Rule]

    def review(self, files: list[ReviewFile]) -> AgentReview:
        findings: list[Finding] = []
        for file in files:
            language = infer_language(file.path, file.language)
            if language not in {"python", "javascript", "typescript", "java", "go", "text"}:
                continue
            ctx = RuleContext(file=file, lines=file.content.splitlines())
            for rule in self.rules:
                finding = rule(self.name, ctx)
                if finding:
                    finding.fingerprint = finding.stable_fingerprint()
                    findings.append(finding)
        return AgentReview(agent=self.name, role=self.role, findings=findings)


RULE_AGENT_BUILDERS: dict[str, tuple[str, str, list[ToolRule]]] = {
    "security": (
        "Security Agent",
        "只关注 SQL 注入、鉴权、敏感信息泄露等安全问题。",
        [
            ("sql_injection_scanner", security_sql_injection),
            ("secret_scanner", security_hardcoded_secret),
            ("authorization_checker", security_missing_authorization),
        ],
    ),
    "performance": (
        "Performance Agent",
        "只关注 N+1 查询、重复 IO、无界查询等性能问题。",
        [
            ("n_plus_one_detector", performance_n_plus_one),
            ("unbounded_query_detector", performance_unbounded_result),
        ],
    ),
    "style": (
        "Style Agent",
        "只关注职责拆分、可维护性、异常路径和测试友好性。",
        [
            ("responsibility_checker", style_too_many_responsibilities),
            ("error_handling_checker", style_missing_error_handling),
        ],
    ),
    "test_coverage": (
        "Test Coverage Agent",
        "关注生产代码变更是否具备相邻或命名匹配的测试覆盖。",
        [],
    ),
}


def build_default_agents(configs: list[object] | None = None) -> list[RuleBasedAgent]:
    if configs:
        agents: list[RuleBasedAgent] = []
        for item in configs:
            if getattr(item, "kind", "") != "rule" or not getattr(item, "enabled", False):
                continue
            agent_key = str(getattr(item, "agent_key", ""))
            builder = RULE_AGENT_BUILDERS.get(agent_key)
            if not builder:
                continue
            _, _, tool_rules = builder
            if agent_key == "test_coverage":
                agents.append(TestCoverageAgent(name=str(getattr(item, "name")), role=str(getattr(item, "role"))))
                continue
            enabled_tools = set(getattr(item, "tools", []) or [])
            rules = [rule for tool, rule in tool_rules if not enabled_tools or tool in enabled_tools]
            agents.append(
                RuleBasedAgent(
                    name=str(getattr(item, "name")),
                    role=str(getattr(item, "role")),
                    rules=rules,
                )
            )
        return agents

    agents: list[RuleBasedAgent] = [
        RuleBasedAgent(name=name, role=role, rules=[rule for _, rule in tool_rules])
        for key, (name, role, tool_rules) in RULE_AGENT_BUILDERS.items()
        if key != "test_coverage"
    ]
    agents.append(TestCoverageAgent())
    return agents
