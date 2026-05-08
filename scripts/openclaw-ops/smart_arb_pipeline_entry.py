#!/usr/bin/env python3
"""Project-specific entrypoint for SmartMultiPlatformArbitrage pipeline runs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_KEY = "smart-multi-platform-arbitrage"
RUNTIME_HOME = Path("/home/arbops/.hermes")
PROJECT_DIR = Path("/home/arbops/projects/SmartMultiPlatformArbitrage")
HARDFLOW_REPO_DIR = Path(
    os.environ.get("HARDFLOW_WORKFLOW_REPO", "")
    or os.environ.get("OPENCLAW_WORKFLOW_REPO", "")
    or "/home/arbops/projects/openclaw-hardflow-backup-20260302"
)
OPS_DIR = RUNTIME_HOME / "ops"
RUNNER = OPS_DIR / "pipeline_runner.py"
BRIDGE = OPS_DIR / "smart_arb_live_bridge.py"
TASK_EXECUTOR_RUNNER = OPS_DIR / "policy" / "task_executor_runner.py"
WORKSPACE_ROOT = RUNTIME_HOME / "pipeline-runs"
PROJECT_MEMORY_ROOT = PROJECT_DIR / "memory"
TASK_CENTER_DB = OPS_DIR / "task-center" / "task_center.db"
LOCAL_POLICY_DIR = Path(__file__).resolve().parents[2] / "skills" / "library" / "control-plane-ops" / "scripts" / "policy"
DEFAULT_REVIEWER_B_PROVIDER = "kimi-coding"
DEFAULT_REVIEWER_B_MODEL = "kimi-k2.6"
DEFAULT_REVIEWER_FALLBACK_MODELS = "zai/glm-5.1,zhipu/glm-5.1,openai-codex/gpt-5.5"
STAGE_AGENT_MAP = {
    "intake": "coordinator",
    "context_snapshot": "project-agent",
    "project_memory_context": "project-agent",
    "external_research": "web-agent",
    "requirements_package": "project-agent",
    "requirements_discussion": "project-agent,reviewer",
    "requirements_review": "reviewer",
    "solution_package": "project-agent",
    "solution_review": "reviewer",
    "code_execution": "backend-dev",
    "verification": "tester",
    "code_review": "reviewer",
    "deployment": "deployer",
    "acceptance": "tester",
    "writeback": "doc-writer",
    "git_publish": "coordinator",
}
FRONTEND_KEYWORDS = (
    "frontend",
    "front-end",
    "ui",
    "ux",
    "react",
    "vue",
    "页面",
    "前端",
    "样式",
    "交互",
    "按钮",
    "表单",
    "组件",
)
BACKEND_KEYWORDS = (
    "backend",
    "api",
    "database",
    "db",
    "service",
    "strategy",
    "后端",
    "接口",
    "数据库",
    "服务",
    "策略",
)
STAGE_LABELS = {
    "intake": "任务接入",
    "context_snapshot": "上下文快照",
    "project_memory_context": "项目记忆读取",
    "git_repository_context": "Git 仓库上下文",
    "graphify_context": "图谱上下文",
    "external_research": "外部资料核对",
    "requirements_package": "需求整理",
    "requirements_discussion": "双 AI 需求讨论",
    "requirements_review": "需求评审",
    "solution_package": "方案整理",
    "graphify_scope_validation": "图谱范围校验",
    "solution_review": "方案评审",
    "plan_publish": "群发方案",
    "risk_gate": "风险门禁",
    "code_execution": "代码执行",
    "verification": "验证",
    "code_review": "代码审查",
    "deployment": "内部部署",
    "acceptance": "验收",
    "writeback": "记忆写回",
    "git_publish": "Git 发布",
}
SHORT_EVIDENCE_LIMIT = 20
ARTIFACT_EVIDENCE_LABELS = {
    "run_meta.json": "接入元数据",
    "context_snapshot.md": "上下文快照",
    "project_memory_context.md": "项目记忆",
    "research_report.md": "外部核对报告",
    "requirements.md": "需求整理报告",
    "requirements_discussion.md": "需求讨论报告",
    "requirements_review.md": "需求评审报告",
    "resolved_requirement.md": "需求确认报告",
    "delivery_plan.json": "交付计划契约",
    "solution.md": "方案整理报告",
    "solution_review.md": "方案评审报告",
    "group_plan_publish.md": "群发执行方案",
    "pre_execution_risk.json": "执行风险门禁",
    "failure_summary.md": "失败群发摘要",
    "patch_summary.md": "代码补丁摘要",
    "verification_report.md": "验证报告",
    "code_review.md": "代码审查报告",
    "deployment_report.md": "部署烟测报告",
    "delivery_evidence.md": "验收证据",
    "writeback_report.md": "记忆写回报告",
    "git_publish_report.md": "Git发布报告",
    "git_repository_context.md": "Git仓库上下文",
    "graphify_context.md": "图谱上下文",
    "graphify_scope_validation.md": "图谱范围校验",
    "graphify_scope_validation.json": "图谱校验数据",
    "pipeline_state.json": "流水线状态",
}
STAGE_ORDER = {name: index for index, name in enumerate(STAGE_LABELS)}
PIPELINE_ROUTE_CHOICES = {"coding_workflow", "todo_auto_candidate"}
NON_PIPELINE_ROUTE_CHOICES = {"direct_run", "requirement_discussion", "specified_agent"}
VALID_ROUTE_CHOICES = PIPELINE_ROUTE_CHOICES | NON_PIPELINE_ROUTE_CHOICES
ROUTE_SELECTION_OPTIONS = (
    ("direct_run", "直接运行", "当前 Discord profile 直接处理，不进入 coordinator pipeline。"),
    ("requirement_discussion", "需求探讨", "先澄清目标、范围、风险和验收，不改代码。"),
    ("specified_agent", "指定 agent", "用户指定具体 agent/owner 后创建 Task Center 任务并分配执行。"),
    ("coding_workflow", "指定编码工作流", "进入完整 coordinator pipeline，包含测试、审查和写回门禁。"),
    ("todo_auto_candidate", "TODO 自动候选", "确认后才允许 backlog runner 作为受控候选推进。"),
)
DIRECT_RUN_RECOMMENDATION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:git\s+(?:fetch|pull|status)|pull\s+(?:latest|code)|sync\s+(?:latest|repo|code))\b",
        r"(?:拉取|同步|更新).{0,12}(?:最新代码|代码|仓库|main|origin/main)",
        r"(?:不要走工作流|不走\s*workflow|绕过工作流|别进\s*pipeline|直接沟通|先自己开发|这次不用自动流程)",
        r"(?:修|改|检查|排查).{0,20}(?:workflow|工作流|pipeline|profile|SOUL|runtime|git_publish|auto-repair|dual review|runtime installer|cron)",
        r"(?:只读|查询|看看|状态|监控|health|strategy/status)",
    )
]
REQUIREMENT_DISCUSSION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:讨论|方案|评估|解释|为什么|是否|能不能|怎么做)",
        r"\b(?:discuss|plan|evaluate|explain|why|whether|how)\b",
    )
]
CODING_WORKFLOW_RECOMMENDATION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:实现|开发|修复|修改|重构|测试|部署|上线|提交|推送|安装依赖|改业务配置|重启业务服务)",
        r"\b(?:implement|develop|fix|change|refactor|test|deploy|push|install|restart)\b",
    )
]
COMMAND_ARTIFACT_RE = re.compile(r"^command_(?P<stage>.+)_(?P<index>\d+)$")
STATUS_LABELS = {
    "completed": "完成",
    "blocked": "阻塞",
    "failed": "失败",
    "passed": "通过",
}
REPAIRABLE_NEXT_ACTIONS = {
    "run_external_research",
    "revise_solution",
    "return_to_code_execution",
    "return_to_deployment",
    "fix_memory_writeback",
    "fix_git_publish",
}
HIGH_RISK_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:api[_ -]?keys?|secrets?|passwords?|credentials?|private\s+keys?|cookies?|jwt|(?:access|refresh|bearer|auth|api|csrf)[_ -]?tokens?)\b\s*[:=]",
        r"\b(?:need|needs|requires?|read|print|show|dump|export|upload|commit|use|modify|delete)\b.{0,60}\b(?:api[_ -]?keys?|secrets?|passwords?|credentials?|private\s+keys?|cookies?|sessions?|session(?:id|_id)?|(?:access|refresh|bearer|auth|api|csrf)[_ -]?tokens?)\b",
        r"\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token|x-csrf-token)\b\s*[:=]",
        r"\b(?:risk=high.{0,120}blocking=true|blocking=true.{0,120}risk=high)\b",
        r"\brule=(?:known_secret_pattern|high_entropy_secret_value|sensitive_header_assignment|sensitive_assignment|private_key_marker|private_key_material)\b",
        r"PRODUCTION_TRADING_ENABLED\s*=\s*true",
        r"\b(?:withdraw(?:als?)?|transfer\s+funds|place\s+orders?|submit\s+orders?|enable\s+(?:real|live)\s+trading|start\s+(?:real|live)\s+trading)\b",
        r"\b(?:need|needs|requires?|start|enable|execute|place|submit|perform|allow)\b.{0,60}\b(?:withdrawals?|transfer\s+funds|funds?\s+(?:movement|operation|transfer)|place\s+orders?|real\s+trading|live\s+trading)\b",
        r"\brm\s+-rf\b",
        r"\bdrop\s+table\b",
        r"\btruncate\s+table\b",
        r"\bforce\s+push\b",
        r"(?:需要|要求|读取|查看|输出|打印|提交|上传|使用|修改|删除).{0,20}(?:密钥|凭证|(?<!stock_)token|cookie|私钥|会话)",
        r"(?:下单|划转|转账|提现|出金|资金操作)",
        r"(?:需要|要求|启动|启用|执行|进行|允许).{0,20}(?:真实交易|实盘交易|下单|划转|转账|提现|出金|资金操作)",
        r"(?:真实交易|实盘交易).{0,20}(?:授权|开启|执行)",
    )
]
SAFE_NEGATED_RISK_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:do\s+not|don't|never|without|no)\b.{0,80}\b(?:credentials?|secrets?|passwords?|private\s+keys?|cookies?|sessions?|tokens?|api[_ -]?keys?|live\s+trading|real\s+trading|orders?|funds?|withdraw|transfer)\b",
        r"(?:不得|不要|不能|禁止|不允许|不涉及|无需|无须|不会|保持|未启动|不启动|不下单|不划转|不读取|不泄露|不发现|未发现|不是.{0,20}(?:硬风险|安全硬停)).{0,80}(?:凭证|密钥|token|cookie|私钥|真实交易|实盘交易|下单|划转|转账|提现|出金|资金|credential|secret|cookie|auth[-_ ]?state|force\s+push)",
        r"(?:凭证|密钥|token|cookie|私钥|真实交易|实盘交易|下单|划转|转账|提现|出金|资金).{0,30}(?:不得|不要|不能|禁止|不允许|不涉及|无需|无须|不会|关闭|false)",
    )
]
RISK_CLAUSE_SPLIT_RE = re.compile(
    r"[\r\n.;；。!?！？,，]+|\b(?:but|however|yet|and)\b|(?:但|但是|不过|然而|并且|并|且|同时)",
    re.IGNORECASE,
)
NEGATED_CLAUSE_RE = re.compile(
    r"^\s*(?:(?:do\s+not|don't|never|without|no)\b|不得|不要|不能|禁止|不允许|不涉及|无需|无须|不会|保持|未启动|不启动|不下单|不划转|不读取|不泄露)",
    re.IGNORECASE,
)
SAFE_NEGATED_COORDINATE_RE = re.compile(
    r"\b(?:or|nor)\s+(?:use|read|print|show|dump|export|upload|commit|modify|move|delete|place|start|enable|execute|transfer|withdraw|read/print|read/print/move|read/print/move/modify)?\s*"
    r"(?:credentials?|secrets?|passwords?|private\s+keys?|cookies?|sessions?|tokens?|api[_ -]?keys?|live\s+trading|real\s+trading|orders?|funds?|withdraw(?:als?)?|transfer\s+funds|place\s+orders?|submit\s+orders?)\b",
    re.IGNORECASE,
)
SAFE_NEGATED_CN_COORDINATE_RE = re.compile(r"(?:或|或者|以及|和)(?:读取|泄露|使用|输出|打印|查看|启动|启用|执行|进行|允许|下单|划转|转账|提现|出金)?(?:凭证|密钥|token|cookie|私钥|真实交易|实盘交易|下单|划转|转账|提现|出金|资金)")
SAFE_NEGATED_FRAGMENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:do\s+not|don't|never|without|no)\b\s+(?:withdraw(?:als?)?|transfer\s+funds|place\s+orders?|submit\s+orders?|enable\s+(?:real|live)\s+trading|start\s+(?:real|live)\s+trading)\b",
        r"\b(?:do\s+not|don't|never|without|no)\b\s+(?:use|read|print|show|dump|export|upload|commit|modify|move|delete|place|start|enable|execute|transfer|withdraw|read/print|read/print/move|read/print/move/modify)?\s*(?:credentials?|secrets?|passwords?|private\s+keys?|cookies?|sessions?|tokens?|api[_ -]?keys?|live\s+trading|real\s+trading|orders?|funds?|withdrawals?|transfer\s+funds)\s*(?:required|needed|used|enabled|disabled)?",
        r"\bkeep\s+(?:live\s+trading|real\s+trading|orders?|funds?|withdrawals?|transfers?)\s+disabled\b",
        r"\bno\s+`?PRODUCTION_TRADING_ENABLED\s*=\s*true`?\s+(?:was\s+)?(?:found|detected|present|residual)\b",
        r"\b(?:found|detected)\s+no\s+`?PRODUCTION_TRADING_ENABLED\s*=\s*true`?\b",
        r"\bno\s+`?PRODUCTION_TRADING_ENABLED\s*=\s*true`?\s+(?:residual\s+)?(?:was\s+)?(?:found|detected|present)?\b",
        r"(?:没有|未发现|未检测到|不存在).{0,40}`?PRODUCTION_TRADING_ENABLED\s*=\s*true`?",
        r"(?:不得|不要|不能|禁止|不允许|不涉及|无需|无须|不会|保持|未启动|不启动|不下单|不划转|不转账|不提现|不出金|不读取|不泄露)(?:读取|泄露|使用|输出|打印|查看|启动|启用|执行|进行|允许|下单|划转|转账|提现|出金)?(?:凭证|密钥|token|cookie|私钥|真实交易|实盘交易|下单|划转|转账|提现|出金|资金)?(?:关闭|false)?",
        r"(?:凭证|密钥|token|cookie|私钥|真实交易|实盘交易|下单|划转|转账|提现|出金|资金)(?:不得|不要|不能|禁止|不允许|不涉及|无需|无须|不会|关闭|false)",
    )
]
SAFE_NEGATED_LIST_FRAGMENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:do\s+not|don't|never|without)\b(?:(?![\r\n.;；。!?！？]).){0,260}\b(?:place\s+orders?|submit\s+orders?|transfer\s+funds|withdraw(?:als?)?|live\s+trading|real\s+trading)\b(?:(?![\r\n.;；。!?！？]).){0,120}",
        r"\b(?:no\s+need(?:ed)?\s+for|do\s+not\s+need|don't\s+need|not\s+(?:required|needed))\b.{0,120}\b(?:api[_ /-]?keys?|secrets?|passwords?|credentials?|credential-imports|private\s+keys?|cookies?|sessions?|session(?:id|_id)?|jwt|tokens?|oauth|authorization|auth\s+state\s+files?)\b\s*(?::|=)?\s*(?:\[[^\]]*REDACTED[^\]]*\])?",
        r"\b(?:do\s+not|don't|never|without)\b\s*(?:(?:use|read|print|show|dump|export|upload|commit|modify|delete|move|place|start|enable|execute|transfer|withdraw|set|configure|turn\s+on|switch\s+on|read/print|read/print/move|read/print/move/modify)\s+)?(?:(?![\r\n.;；。!?！？]|\b(?:but|however|yet|then|needs?|requires?|set|configure|turn\s+on|switch\s+on|start|enable|execute|place|submit|perform|allow)\b).){0,260}\b(?:api[_ /-]?keys?|secrets?|passwords?|credentials?|credential-imports|private\s+keys?|cookies?|sessions?|session(?:id|_id)?|jwt|tokens?|oauth|auth\s+state\s+files?|live\s+trading|real\s+trading|orders?|funds?|withdraw(?:als?)?|transfer\s+funds|place\s+orders?|submit\s+orders?)\b",
        r"\b(?:do\s+not|don't|never|without)\b\s*(?:(?:set|configure)\s+)?(?:(?![\r\n.;；。!?！？]|\b(?:but|however|yet|and|then|needs?|requires?|set|configure|turn\s+on|switch\s+on|start|enable|execute|place|submit|perform|allow)\b).){0,160}\bPRODUCTION_TRADING_ENABLED\s*=\s*true\b",
        r"(?:不得|不要|不能|禁止|不允许|不涉及|无需|无须|不会|保持|未在|未启动|未下单|未划转|未转账|未提现|未出金|未读取|未泄露|未打印|未移动|未修改|未保留|不保留|不启动|不下单|不划转|不转账|不提现|不出金|不读取|不泄露|不打印|不移动|不修改|不发现|未发现|不是.{0,20}(?:硬风险|安全硬停))(?:(?![\r\n.;；。!?！？]|(?:但|但是|不过|然而|并且|然后|需要|要求|设置|配置|打开|开启|启动|启用|执行|进行|允许|下单后|划转后|转账后|提现后|出金后|资金操作)).){0,200}(?:凭证|密钥|token|cookie|私钥|真实交易|实盘交易|交易|下单|划转|转账|提现|出金|资金|credential(?:-imports)?|credentials?|secrets?|tokens?|cookies?|oauth|auth[-_ ]?state|force\s+push|api[_ /-]?keys?)",
        r"(?:不得|不要|不能|禁止|不允许|不应|不会)(?:(?![\r\n.;；。!?！？]|(?:但|但是|不过|然而|并且|然后|需要|要求|设置|配置|打开|开启|启动|启用|执行|进行|允许)).){0,160}PRODUCTION_TRADING_ENABLED\s*=\s*true",
    )
]
SAFE_DOCUMENTATION_HISTORY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:按用户要求|已|已经).{0,30}从待办中删除.{0,80}(?:凭证|密钥|token|cookie|安全轮换).{0,80}(?:事项|TODO|任务|跟踪)",
        r"未在.{0,40}(?:文档|输出|日志).{0,40}(?:保留|记录|包含).{0,80}(?:token|key|pat|密钥|凭证|cookie).{0,40}(?:明文)?",
        r"(?:触发点|触发项|原因|自动修复判断).{0,80}(?:风险规则|high|高风险|文本中仍出现).{0,160}(?:真实交易|实盘交易|下单|划转|转账|提现|出金|资金操作|资金动作|凭证|密钥|token|cookie)",
        r"(?:原因|reasons?)\s*[:=：].{0,260}(?:\\[bBsSdDwW]|\(\?:|\{0,\d+\}|\[A-Za-z|\[\\^).{0,260}",
        r"(?:没有|未|不曾).{0,80}(?:credential|auth|凭证|真实交易|实盘交易|下单|划转|转账|提现|出金|资金操作|资金动作|force\s+push|破坏性).{0,80}(?:硬风险|硬阻塞|风险|阻塞)",
        r"(?:fail\s+on|安全扫描|Diff\s+safety\s+scan|新增行扫描).{0,220}(?:PRODUCTION_TRADING_ENABLED\s*=\s*true|place_order|transfer|withdraw|credential|auth|真实交易|下单|划转|提现)",
        r"(?:forbidden_targets?|forbidden|禁止目标|安全边界).{0,260}(?:real\s+trading|orders?|transfer|withdraw|credential|auth|force\s+push|真实交易|下单|划转|提现|凭证|密钥)",
        r"(?:new\s+Hyperliquid\s+real\s+stock-token\s+adapter\s+files|real\s+trading/order/transfer/withdrawal/control\s+write\s+paths|真实交易/下单/划转/提现/控制写路径|未发现.{0,260}PRODUCTION_TRADING_ENABLED\s*=\s*true|确认未启用.{0,120}PRODUCTION_TRADING_ENABLED\s*=\s*true|reset/stash/checkout.{0,80}force\s+push|no\s+`?reset`?.{0,160}force\s+push|未发现.{0,160}(?:下单|划转|转账|提现|出金|资金操作)|只做最小安全口径修正)",
        r"(?:没有|未|不曾).{0,20}(?:启动|执行|进行|发生|完成)?(?:真实交易|实盘交易|下单|划转|转账|提现|出金|资金操作|资金动作)",
    )
]
SERVICE_CONTROL_DENY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"不触碰服务控制",
        r"不触碰服务",
        r"不修改服务",
        r"不需要.{0,10}(?:重启|部署)",
        r"不重启",
        r"不部署",
        r"不要.{0,20}(?:重启|部署|改动服务|触碰服务)",
        r"\bdo\s+not\s+(?:restart|deploy|touch\s+service|modify\s+service)",
        r"\bwithout\s+(?:service\s+control|deployment|restart)",
        r"\bno\s+(?:service\s+control|deployment|restart)",
    )
]
MEMORY_DOC_ONLY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:只|仅)写入.{0,60}(?:memory|记忆|docs|文档|长期事实)",
        r"写回.{0,60}(?:memory|记忆|docs|文档|长期事实).{0,40}(?:不触碰|不要|不修改|不重启|不部署)",
        r"\b(?:memory|docs?|documentation)[-/ ]?only\b",
    )
]
POSITIVE_DEPLOYMENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:重启|部署|上线|发布|启动).{0,30}(?:服务|API|FastAPI|内控|完成部署)?",
        r"\b(?:restart|deploy|deployment|rollout|smoke)\b",
    )
]
PRE_REDACTED_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_ -]?key|secret|password|credential|session(?:id|_id)?|"
    r"(?:access|refresh|bearer|auth|api|csrf)[_ -]?token)\b\s*[:=]\s*\[[^\]]*REDACTED[^\]]*\]"
)
PRE_REDACTED_HEADER_RE = re.compile(
    r"(?im)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token|"
    r"x-csrf-token|session(?:id|_id)?|csrf(?:token)?|jwt)\b\s*[:=]\s*\[[^\]]*REDACTED[^\]]*\]"
)
PRE_REDACTED_MARKER_RE = re.compile(
    r"__SMART_ARB_PRE_REDACTED__(?P<key>[A-Za-z0-9_-]+)(?P<sep>[:=])\[REDACTED\]__"
)
NEGATED_PRE_REDACTED_CONTEXT_RE = re.compile(
    r"(?i)\b(?:no\s+need(?:ed)?\s+for|do\s+not\s+need|don't\s+need|not\s+(?:required|needed))\b|"
    r"(?:不需要|无需|无须)"
)
SENSITIVE_ACTION_CONTEXT_RE = re.compile(
    r"(?i)\b(?:need|needs|required?|requires?|missing|read|print|show|dump|export|upload|"
    r"commit|use|modify|delete|provide|set|configure|add)\b|"
    r"(?:需要|要求|缺少|未配置|读取|打印|展示|输出|导出|上传|提交|使用|修改|删除|配置|提供|填入|设置)"
)
SENSITIVE_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9_-]{47,}(?![A-Za-z0-9])")
KNOWN_SECRET_RE = re.compile(
    r"(?<![A-Za-z0-9_])("
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"sk-[A-Za-z0-9][A-Za-z0-9_-]{16,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"hf_[A-Za-z0-9]{20,}|"
    r"AIza[0-9A-Za-z_-]{20,}|"
    r"ya29\.[0-9A-Za-z_-]{20,}|"
    r"AKIA[0-9A-Z]{16}"
    r")(?![A-Za-z0-9_])"
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])['\"`]?("
    r"authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token|x-csrf-token|"
    r"[A-Z0-9_]*(?:API[_-]?KEY|SECRET|PASSWORD|PASS|TOKEN|COOKIE|OAUTH|PRIVATE[_-]?KEY|SESSION(?:ID|_ID)?|CREDENTIAL)[A-Z0-9_]*|"
    r"api[_ -]?key|secret|password|credential|session(?:id|_id)?|"
    r"(?:access|refresh|bearer|auth|api|csrf)[_ -]?token)['\"`]?\s*[:=]\s*([^\s,;]+)"
)
SENSITIVE_HEADER_RE = re.compile(
    r"(?im)\b(authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token|"
    r"x-csrf-token|session(?:id|_id)?|csrf(?:token)?|jwt)\b\s*[:=]\s*([^\r\n]+)"
)
PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)


def utc_run_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_prefix = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in prefix).strip("-")
    return f"{safe_prefix or 'discord'}-{stamp}"


def option_present(args: list[str], option: str) -> bool:
    return any(item == option or item.startswith(option + "=") for item in args)


def compact_text(value: object, limit: int = 120) -> str:
    text = " ".join(redact_text(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def redact_text(value: object) -> str:
    text = str(value or "")
    held_markers: list[str] = []

    def hold_marker(match: re.Match) -> str:
        held_markers.append(match.group(0))
        return f"__SMART_ARB_HELD_MARKER_{len(held_markers) - 1}__"

    text = PRIVATE_KEY_BLOCK_RE.sub("[REDACTED_PRIVATE_KEY]", text)
    text = PRE_REDACTED_MARKER_RE.sub(hold_marker, text)
    text = SENSITIVE_HEADER_RE.sub(lambda match: f"{match.group(1)}: [REDACTED]", text)
    text = SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = KNOWN_SECRET_RE.sub("[REDACTED]", text)
    text = SENSITIVE_TOKEN_RE.sub("[REDACTED]", text)
    for index, marker in enumerate(held_markers):
        text = text.replace(f"__SMART_ARB_HELD_MARKER_{index}__", marker)
    return text


def strip_safe_negated_fragments(text: str) -> str:
    cleaned = text
    for pattern in SAFE_NEGATED_LIST_FRAGMENT_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned


def strip_safe_documentation_history(text: str) -> str:
    cleaned = text
    for pattern in SAFE_DOCUMENTATION_HISTORY_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned


REGEX_PATTERN_CLAUSE_RE = re.compile(r"(?:\\[bBsSdDwW]|\(\?:|\{0,\d+\}|\[A-Za-z|\[\\^).{0,220}")


def is_regex_pattern_clause(text: str) -> bool:
    value = str(text or "")
    return bool(REGEX_PATTERN_CLAUSE_RE.search(value))


def mark_pre_redacted_sensitive_markers(text: str) -> str:
    def replacement(match: re.Match, separator: str) -> str:
        key = re.sub(r"[^A-Za-z0-9_-]+", "_", match.group(1).strip()).strip("_").lower()
        return f"__SMART_ARB_PRE_REDACTED__{key}{separator}[REDACTED]__"

    text = PRE_REDACTED_HEADER_RE.sub(lambda match: replacement(match, ":"), text)
    return PRE_REDACTED_ASSIGNMENT_RE.sub(lambda match: replacement(match, "="), text)


def restore_or_strip_pre_redacted_sensitive_markers(text: str) -> str:
    if PRE_REDACTED_MARKER_RE.search(text) and NEGATED_PRE_REDACTED_CONTEXT_RE.search(text):
        return PRE_REDACTED_MARKER_RE.sub(" ", text)
    if SENSITIVE_ACTION_CONTEXT_RE.search(text):
        return PRE_REDACTED_MARKER_RE.sub(
            lambda match: f"{match.group('key')}{match.group('sep')}[REDACTED]",
            text,
        )
    return PRE_REDACTED_MARKER_RE.sub(" ", text)


def risk_scan_text(value: object) -> str:
    text = redact_text(mark_pre_redacted_sensitive_markers(str(value or "")))
    if is_regex_pattern_clause(text):
        return ""
    text = strip_safe_negated_fragments(strip_safe_documentation_history(text))
    clauses = [clause.strip() for clause in RISK_CLAUSE_SPLIT_RE.split(text) if clause.strip()]
    risky_clauses = []
    for clause in clauses:
        if is_regex_pattern_clause(clause):
            continue
        cleaned_clause = strip_safe_negated_fragments(strip_safe_documentation_history(clause))
        cleaned_clause = restore_or_strip_pre_redacted_sensitive_markers(cleaned_clause)
        for pattern in SAFE_NEGATED_FRAGMENT_PATTERNS:
            cleaned_clause = pattern.sub(" ", cleaned_clause)
        if NEGATED_CLAUSE_RE.search(clause):
            cleaned_clause = SAFE_NEGATED_COORDINATE_RE.sub(" ", cleaned_clause)
            cleaned_clause = SAFE_NEGATED_CN_COORDINATE_RE.sub(" ", cleaned_clause)
        if not cleaned_clause.strip() and any(pattern.search(clause) for pattern in SAFE_NEGATED_RISK_PATTERNS):
            continue
        risky_clauses.append(cleaned_clause)
    return "\n".join(risky_clauses)


def parse_runner_state(stdout: str) -> dict | None:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) and "stages" in payload else None


def parse_json_payload(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {}
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def normalize_route_choice(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def recommend_discord_route(requirement: str) -> tuple[str, str]:
    text = str(requirement or "").strip()
    if any(pattern.search(text) for pattern in DIRECT_RUN_RECOMMENDATION_PATTERNS):
        return "direct_run", "需求可由当前 Discord profile 直接受控处理，推荐先选择 direct_run。"
    if any(pattern.search(text) for pattern in REQUIREMENT_DISCUSSION_PATTERNS):
        return "requirement_discussion", "需求更像沟通或方案问题，推荐先选择 requirement_discussion。"
    if any(pattern.search(text) for pattern in CODING_WORKFLOW_RECOMMENDATION_PATTERNS):
        return "coding_workflow", "需求涉及实现、验证或交付门禁，推荐选择 coding_workflow。"
    return "direct_run", "未命中必须进入 pipeline 的信号，推荐先选择 direct_run。"


def render_route_selection_card(*, source: str, profile: str, requirement: str) -> str:
    recommended_route, reason = recommend_discord_route(requirement)
    lines = [
        "# nofx 执行链路选择",
        f"来源: {source}/{profile}",
        "总状态: 等待人工选择",
        f"推荐链路: {recommended_route}",
        f"推荐原因: {reason}",
        "",
        "可选项",
    ]
    for route_id, label, description in ROUTE_SELECTION_OPTIONS:
        lines.append(f"- {route_id}: {label}；{description}")
    lines.extend(
        [
            "",
            "下一步: 请回复其中一个选项。选择 `specified_agent` 必须同时指定 agent；选择 `coding_workflow` 或 `todo_auto_candidate` 后启动 coordinator pipeline。",
            "防误触发: 当前调用没有携带人工选择凭证，已阻止直接启动 `smart-arb-pipeline`。",
            "回答状态: 等待人工选择",
        ]
    )
    return "\n".join(lines)


def route_selection_payload(*, source: str, profile: str, requirement: str) -> dict[str, object]:
    recommended_route, reason = recommend_discord_route(requirement)
    return {
        "status": "blocked",
        "next_action": "await_route_selection",
        "source": source,
        "profile": profile,
        "stages": [],
        "answer_status": "等待人工选择",
        "route_selection": {
            "mode": "manual_selection",
            "required": True,
            "recommended_route": recommended_route,
            "recommendation_reason": reason,
            "options": [
                {"id": route_id, "label": label, "description": description}
                for route_id, label, description in ROUTE_SELECTION_OPTIONS
            ],
        },
    }


def discord_route_choice_required(source: str) -> bool:
    if str(source or "").strip().lower() != "discord":
        return False
    return env_flag("SMART_ARB_REQUIRE_DISCORD_ROUTE_CHOICE", True)


def should_block_for_discord_route_choice(source: str, route_choice: str) -> bool:
    if not discord_route_choice_required(source):
        return False
    return normalize_route_choice(route_choice) not in (PIPELINE_ROUTE_CHOICES | {"specified_agent"})


def short_evidence_label(label: str, limit: int = SHORT_EVIDENCE_LIMIT) -> str:
    compacted = "".join(str(label or "").split())
    return compacted[:limit]


def artifact_evidence_label(name: str, *, stage: str = "") -> str:
    clean_name = Path(str(name or "").strip()).name
    if not clean_name:
        return ""
    mapped = ARTIFACT_EVIDENCE_LABELS.get(clean_name)
    if mapped:
        return short_evidence_label(mapped)
    if clean_name.startswith("auto_repair_context_"):
        return "自动修复上下文"
    if clean_name.startswith("rollback_"):
        return "回滚记录"
    if stage:
        stage_label = STAGE_LABELS.get(stage, stage)
        return short_evidence_label(f"{stage_label}证据")
    stem = clean_name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
    return short_evidence_label(stem or clean_name)


def stage_artifact_name(stage: dict) -> str:
    artifact = str(stage.get("artifact") or "").strip()
    if not artifact:
        return ""
    return artifact_evidence_label(artifact, stage=str(stage.get("name") or "").strip())


def read_json_file(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_text_excerpt(path: Path, limit: int = 420) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return compact_text(text, limit)


def read_artifact_excerpt(state: dict | None, key: str, limit: int = 900) -> str:
    if not isinstance(state, dict):
        return ""
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
    path = artifact_path(artifacts.get(key), str(state.get("run_dir") or ""))
    if path is None:
        return ""
    return read_text_excerpt(path, limit)


def risk_gate_summary(state: dict | None) -> dict:
    if not isinstance(state, dict):
        return {}
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
    path = artifact_path(artifacts.get("pre_execution_risk"), str(state.get("run_dir") or ""))
    if path is None:
        return {}
    return read_json_file(path)


def group_publish_excerpt(state: dict | None, *, failure: bool = False, limit: int = 900) -> str:
    key = "failure_summary" if failure else "plan_publish"
    return read_artifact_excerpt(state, key, limit)


def artifact_path(value: object, run_dir: str = "") -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute() or not run_dir:
        return path
    return Path(run_dir) / path


def command_reports(state: dict | None, stage_name: str | None = None) -> list[dict]:
    if not isinstance(state, dict):
        return []
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
    reports: list[dict] = []
    prefix = f"command_{stage_name}_" if stage_name else "command_"
    for key, value in sorted(artifacts.items()):
        if not str(key).startswith(prefix):
            continue
        path = artifact_path(value, str(state.get("run_dir") or ""))
        if path is None:
            continue
        report = read_json_file(path)
        if report:
            report["_artifact_key"] = str(key)
            report["_artifact_path"] = str(path)
            reports.append(report)
    return reports


def agent_invocations(state: dict | None, stage_name: str | None = None) -> list[dict]:
    if not isinstance(state, dict):
        return []
    items = state.get("agent_invocations") if isinstance(state.get("agent_invocations"), list) else []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if stage_name and str(item.get("stage") or "").strip() != stage_name:
            continue
        out.append(item)
    return out


def runtime_ref_parts(*, session_id: str = "", run_id: str = "", session_key: str = "") -> list[str]:
    parts: list[str] = []
    if session_id:
        parts.append(f"session={session_id}")
    if run_id:
        parts.append(f"run={run_id}")
    if session_key:
        parts.append(f"session_key={session_key}")
    return parts


def stage_runtime_ref_parts(state: dict | None, stage_name: str) -> list[str]:
    refs = agent_invocations(state, stage_name)
    if not refs:
        return []
    session_ids = [str(item.get("session_id") or "").strip() for item in refs if str(item.get("session_id") or "").strip()]
    run_ids = [str(item.get("run_id") or "").strip() for item in refs if str(item.get("run_id") or "").strip()]
    parts: list[str] = []
    if session_ids:
        parts.append("session=" + ",".join(session_ids[:2]))
    if run_ids:
        parts.append("run=" + ",".join(run_ids[:2]))
    if not parts:
        parts.append("session=-；run=-")
    return parts


def stage_record(state: dict | None, stage_name: str) -> dict:
    if not isinstance(state, dict):
        return {}
    for item in state.get("stages", []) or []:
        if isinstance(item, dict) and item.get("name") == stage_name:
            return item
    return {}


def failed_stage_record(state: dict | None) -> dict:
    if not isinstance(state, dict):
        return {}
    failed_stage = str(state.get("failed_stage") or "").strip()
    return stage_record(state, failed_stage) if failed_stage else {}


def report_excerpt(report: dict, limit: int = 260, *, redact: bool = True) -> str:
    for key in ("error", "stderr", "stdout"):
        raw = report.get(key)
        text = compact_text(redact_text(raw) if redact else raw, limit)
        if text:
            return text
    return "没有可用输出"


def report_artifact_name(report: dict) -> str:
    path = str(report.get("_artifact_path") or "").strip()
    if path:
        name = Path(path).name
        stage = str(report.get("stage") or "").strip()
        index = str(report.get("index") or "").strip()
        if not index:
            key = str(report.get("_artifact_key") or "").strip()
            match = COMMAND_ARTIFACT_RE.match(key)
            index = match.group("index") if match else ""
        stage_label = STAGE_LABELS.get(stage, stage)
        suffix = index if index and index != "0" else ""
        if stage_label:
            return short_evidence_label(f"{stage_label}命令{suffix}")
        return artifact_evidence_label(name, stage=stage)
    key = str(report.get("_artifact_key") or "").strip()
    match = COMMAND_ARTIFACT_RE.match(key)
    if match:
        stage = match.group("stage")
        return short_evidence_label(f"{STAGE_LABELS.get(stage, stage)}命令{match.group('index')}")
    return ""


def report_line(report: dict, *, include_output: bool = False) -> str:
    stage = str(report.get("stage") or "").strip()
    label = STAGE_LABELS.get(stage, stage or "命令")
    agent = str(report.get("agent_id") or STAGE_AGENT_MAP.get(stage, "agent")).strip()
    returncode = report.get("returncode")
    ok = "通过" if report.get("ok") else "失败"
    parts = [f"{label}: {agent} -> {ok}", f"returncode={returncode}"]
    parts.extend(
        runtime_ref_parts(
            session_id=str(report.get("agent_session_id") or "").strip(),
            run_id=str(report.get("agent_run_id") or "").strip(),
            session_key=str(report.get("agent_session_key") or "").strip(),
        )
    )
    artifact = report_artifact_name(report)
    if artifact:
        parts.append(f"证据={artifact}")
    if include_output or not report.get("ok"):
        output = report_excerpt(report)
        if output and output != "没有可用输出":
            parts.append(f"摘要={output}")
    return "- " + "；".join(parts)


def run_state_path(run_id: str) -> Path:
    return WORKSPACE_ROOT / run_id / "pipeline_state.json"


def human_duration(seconds: float | int) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小时{minutes}分"
    if minutes:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


def latest_command_reports(state: dict | None, limit: int = 3) -> list[dict]:
    reports = command_reports(state)
    count = max(0, int(limit or 0))
    if not reports or count <= 0:
        return []
    return sorted(reports, key=command_report_sort_key)[-count:]


def command_report_sort_key(report: dict) -> tuple[str, int, int, str]:
    timestamp = str(report.get("ended_at") or report.get("started_at") or "").strip()
    stage = str(report.get("stage") or "").strip()
    index = int(report.get("index") or 0)
    artifact_key = str(report.get("_artifact_key") or "").strip()
    match = COMMAND_ARTIFACT_RE.match(artifact_key)
    if match:
        stage = stage or match.group("stage")
        index = index or int(match.group("index") or 0)
    return (timestamp, STAGE_ORDER.get(stage, len(STAGE_ORDER)), index, artifact_key)


def current_stage_record(state: dict | None) -> dict:
    if not isinstance(state, dict):
        return {}
    failed_stage = str(state.get("failed_stage") or "").strip()
    if failed_stage:
        stage = stage_record(state, failed_stage)
        if stage:
            return stage
    stages = [stage for stage in state.get("stages", []) if isinstance(stage, dict)]
    for stage in stages:
        if stage.get("status") != "completed":
            return stage
    return stages[-1] if stages else {}


def answer_status_label(status: str, *, parsed: bool = True, returncode: int = 0) -> str:
    if not parsed:
        return "未回答完毕，无法解析执行结果"
    normalized = str(status or "").strip()
    if normalized == "completed" and returncode == 0:
        return "已回答完毕"
    if normalized == "blocked":
        return "未回答完毕，等待人工确认或自动修复"
    if normalized in {"", "running"}:
        return "正在回复/执行中"
    if returncode != 0:
        return "未回答完毕，执行失败"
    return f"未回答完毕，当前状态={STATUS_LABELS.get(normalized, normalized or '未知')}"


def extract_task_title(text: str, *, fallback: str = "项目任务") -> str:
    """Return a short human task title for Discord status-card headings."""
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if not raw:
        return fallback
    p_match = re.search(r"(P\d+\s*[^。；;，,：:\n]{1,24})", raw, re.IGNORECASE)
    if p_match:
        return compact_text(p_match.group(1).strip(), 32)
    for marker in ("需求", "任务", "修正", "部署", "验收", "实现", "删除"):
        idx = raw.find(marker)
        if 0 <= idx <= 24:
            sentence = re.split(r"[。；;\n]", raw[idx:], maxsplit=1)[0]
            return compact_text(sentence.strip(), 32)
    sentence = re.split(r"[。；;\n]", raw, maxsplit=1)[0]
    return compact_text(sentence.strip(), 32)


def task_title_from_state(state: dict | None, *, fallback: str = "项目任务") -> str:
    if not isinstance(state, dict):
        return fallback
    raw = ""
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
    run_meta_path = str(artifacts.get("run_meta") or "").strip()
    if run_meta_path:
        meta = read_json_file(Path(run_meta_path))
        if isinstance(meta, dict):
            raw = str(meta.get("requirement_preview") or "").strip()
    if not raw:
        raw = str(state.get("requirement_preview") or "").strip()
    return extract_task_title(raw, fallback=fallback)


def render_progress_heading(kind: str, title: str) -> str:
    clean = compact_text(str(title or "项目任务").strip(), 32)
    return f"# nofx {clean}执行{kind}"


def render_progress_start(run_id: str, *, source: str, profile: str, requirement: str = "") -> str:
    run_dir = WORKSPACE_ROOT / run_id
    title = extract_task_title(requirement)
    return "\n".join(
        [
            render_progress_heading("进度", title),
            f"- 任务名称: {title}",
            f"- 来源: {source}/{profile}",
            f"- Run ID: {run_id}",
            f"- 回答状态: {answer_status_label('running')}",
            "- 状态: 已启动 coordinator pipeline，等待第一份阶段状态",
            f"- 证据目录: {run_dir}",
            "- 说明: 后续只输出工作流阶段状态、当前卡点和证据位置；不会展开命令原始输出。",
        ]
    )


def render_progress_update(
    state: dict | None,
    *,
    source: str,
    profile: str,
    elapsed_seconds: float,
    stage_limit: int = 8,
    command_limit: int = 3,
    include_command_output: bool = False,
) -> str:
    if not isinstance(state, dict) or not state:
        return ""
    status = str(state.get("status") or "").strip()
    status_label = "运行中" if status in {"", "running"} else STATUS_LABELS.get(status, status)
    stages = [stage for stage in state.get("stages", []) if isinstance(stage, dict)]
    completed = sum(1 for stage in stages if stage.get("status") == "completed")
    current_stage = current_stage_record(state)
    title = task_title_from_state(state)
    lines = [
        render_progress_heading("进度", title),
        f"- 任务名称: {title}",
        f"- 来源: {source}/{profile}",
        f"- Run ID: {state.get('run_id', '-')}",
        f"- 回答状态: {answer_status_label(status)}",
        f"- 总状态: {status_label or '运行中'}",
        f"- 已运行: {human_duration(elapsed_seconds)}",
        f"- 阶段进度: {completed}/{len(stages)} 完成",
    ]
    run_dir = str(state.get("run_dir") or "").strip()
    if run_dir:
        lines.append(f"- 证据目录: {run_dir}")
    if current_stage:
        lines.append(f"- 当前阶段: {render_stage_line(current_stage, state=state).lstrip('- ')}")
    next_action = str(state.get("next_action") or "").strip()
    failed_stage = str(state.get("failed_stage") or "").strip()
    if next_action and next_action != "none":
        failed_label = STAGE_LABELS.get(failed_stage, failed_stage or "none")
        lines.append(f"- 下一步: {next_action}；失败阶段: {failed_label}")

    if stages:
        visible_stages = stages[-max(1, int(stage_limit or 8)) :]
        lines.append("")
        lines.append("## 最近阶段")
        for stage in visible_stages:
            lines.append(render_stage_line(stage, state.get("stage_agents") if isinstance(state.get("stage_agents"), dict) else None, state))

    reports = latest_command_reports(state, command_limit)
    if reports:
        lines.append("")
        lines.append("## 最近命令状态")
        for report in reports:
            lines.append(report_line(report, include_output=include_command_output))
    return "\n".join(lines)


def failure_evidence(state: dict | None, *, redact: bool = True) -> str:
    if not isinstance(state, dict):
        return ""
    failed_stage = str(state.get("failed_stage") or "").strip()
    stage = failed_stage_record(state)
    parts = [
        str(stage.get("detail") or "").strip(),
        str(state.get("next_action") or "").strip(),
    ]
    for report in command_reports(state, failed_stage):
        parts.extend(
            [
                str(report.get("error") or "").strip(),
                str(report.get("stderr") or "").strip(),
                str(report.get("stdout") or "").strip(),
            ]
        )
    artifact = artifact_path(stage.get("artifact"), str(state.get("run_dir") or ""))
    if artifact:
        parts.append(read_text_excerpt(artifact, 1800))
    text = "\n".join(part for part in parts if part)
    return redact_text(text) if redact else text


REPAIRABLE_REVIEW_CONTRACT_RE = re.compile(
    r"(?:requires_revision|Required revision|Blocking issue|contract drift|delivery_plan|target_files|"
    r"missing from the reviewed workspace|not part of the diff|ignored by git|MISSING|缺失|未进入\s*diff|未交付|未创建)",
    re.IGNORECASE,
)
REPAIRABLE_SOLUTION_PLAN_RE = re.compile(
    r"(?:solution_review|revise_solution|delivery_plan|target_files|must_change_targets|entry_points|"
    r"implementation_steps|api_contracts|verification_commands|方案包|方案合同|目标文件|目标路径|"
    r"移除|剔除|过滤|不得包含|不能进入|remove|exclude|filter|pseudo|伪路径|只读验收|可执行验证)",
    re.IGNORECASE,
)
POSITIVE_SECRET_ACCESS_RE = re.compile(
    r"\b(?:read|print|show|dump|export|upload|commit|use|modify)\b.{0,80}"
    r"\b(?:api[_ -]?keys?|secrets?|passwords?|credentials?|private\s+keys?|cookies?|sessions?|tokens?|auth[-_ ]?state)\b|"
    r"(?:读取|查看|输出|打印|提交|上传|使用|修改).{0,40}(?:密钥|凭证|token|cookie|私钥|会话|auth)",
    re.IGNORECASE,
)


def is_repairable_review_contract_issue(state: dict | None, raw_evidence: str) -> bool:
    if not isinstance(state, dict):
        return False
    next_action = str(state.get("next_action") or "").strip()
    failed_stage = str(state.get("failed_stage") or "").strip()
    if next_action != "return_to_code_execution" or failed_stage not in {"code_review", "solution_review"}:
        return False
    return bool(REPAIRABLE_REVIEW_CONTRACT_RE.search(raw_evidence or ""))


def is_repairable_solution_plan_revision(state: dict | None, raw_evidence: str, evidence: str) -> bool:
    if not isinstance(state, dict):
        return False
    if str(state.get("next_action") or "").strip() != "revise_solution":
        return False
    if str(state.get("failed_stage") or "").strip() != "solution_review":
        return False
    if not REPAIRABLE_SOLUTION_PLAN_RE.search(raw_evidence or ""):
        return False
    if POSITIVE_SECRET_ACCESS_RE.search(evidence or ""):
        return False
    hard_patterns = (
        HIGH_RISK_PATTERNS[0],  # explicit credential/header assignment
        HIGH_RISK_PATTERNS[2],  # sensitive header assignment
        HIGH_RISK_PATTERNS[4],  # secret scanner rules
        HIGH_RISK_PATTERNS[5],  # PRODUCTION_TRADING_ENABLED=true
        HIGH_RISK_PATTERNS[6],  # live trading/order/fund verbs
        HIGH_RISK_PATTERNS[7],  # required trading/fund action
        HIGH_RISK_PATTERNS[8],  # rm -rf
        HIGH_RISK_PATTERNS[9],  # DROP TABLE
        HIGH_RISK_PATTERNS[10],  # TRUNCATE TABLE
        HIGH_RISK_PATTERNS[11],  # force push
        HIGH_RISK_PATTERNS[13],  # fund/trading Chinese terms
        HIGH_RISK_PATTERNS[14],  # required fund/trading Chinese terms
        HIGH_RISK_PATTERNS[15],  # real trading authorization
    )
    return not any(pattern.search(evidence) for pattern in hard_patterns)


def classify_repair_risk(state: dict | None) -> tuple[str, list[str]]:
    if not isinstance(state, dict):
        return "unknown", ["没有可解析的 pipeline 状态"]
    if str(state.get("status") or "") != "blocked":
        return "none", ["当前不是阻塞态"]
    next_action = str(state.get("next_action") or "").strip()
    raw_evidence = failure_evidence(state, redact=False)
    evidence = risk_scan_text(raw_evidence)
    reasons = [pattern.pattern for pattern in HIGH_RISK_PATTERNS if pattern.search(evidence)]
    if reasons:
        if is_repairable_solution_plan_revision(state, raw_evidence, evidence):
            return "medium", [f"可回流方案修订: {next_action}"]
        if is_repairable_review_contract_issue(state, raw_evidence) and not any(
            pattern.search(evidence)
            for pattern in (
                HIGH_RISK_PATTERNS[0],  # explicit credential/header assignment
                HIGH_RISK_PATTERNS[2],  # sensitive header assignment
                HIGH_RISK_PATTERNS[4],  # secret scanner rules
            )
        ):
            return "medium", [f"可回流审查返工: {next_action}"]
        return "high", reasons[:4]
    if next_action in REPAIRABLE_NEXT_ACTIONS:
        return "medium", [f"可回流动作: {next_action}"]
    return "high", [f"不在自动修复白名单: {next_action or 'none'}"]


def should_auto_repair(state: dict | None, attempt_count: int, max_attempts: int) -> tuple[bool, str, list[str]]:
    if max_attempts <= 0:
        return False, "disabled", ["自动修复已关闭"]
    if attempt_count >= max_attempts:
        return False, "exhausted", [f"已达到最大自动修复次数 {max_attempts}"]
    risk, reasons = classify_repair_risk(state)
    if risk == "high":
        return False, risk, reasons
    if risk == "medium":
        return True, risk, reasons
    return False, risk, reasons


def repair_context_markdown(state: dict, attempt: int, risk: str, reasons: list[str]) -> str:
    failed_stage = str(state.get("failed_stage") or "unknown")
    next_action = str(state.get("next_action") or "unknown")
    evidence = compact_text(failure_evidence(state), 2200)
    return "\n".join(
        [
            "# Smart Arb Auto Repair Context",
            "",
            f"- Attempt: {attempt}",
            f"- Previous run: {state.get('run_id', '-')}",
            f"- Failed stage: {failed_stage}",
            f"- Next action: {next_action}",
            f"- Risk class: {risk}",
            f"- Decision reason: {', '.join(reasons) if reasons else 'repairable pipeline block'}",
            "",
            "## Previous Failure Evidence",
            evidence or "No detailed failure evidence was available.",
            "",
            "## Repair Contract",
            "- Repair through the normal pipeline stages; do not bypass verification, code review, deployment, memory writeback, or git publish.",
            "- Fix the root cause if it is within the repository/runtime permissions.",
            "- Stop and report if the next step requires secrets, real trading authorization, fund movement, or destructive data operations.",
        ]
    )


def write_repair_context_file(
    state: dict,
    attempt: int,
    risk: str,
    reasons: list[str],
    content: str | None = None,
) -> Path | None:
    raw_run_dir = str(state.get("run_dir") or "").strip()
    if not raw_run_dir:
        return None
    run_dir = Path(raw_run_dir).expanduser()
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"auto_repair_context_{attempt}.md"
        path.write_text(content or repair_context_markdown(state, attempt, risk, reasons), encoding="utf-8")
        return path
    except OSError:
        return None


def render_stage_line(stage: dict, stage_agents: dict | None = None, state: dict | None = None) -> str:
    name = str(stage.get("name") or "").strip()
    label = STAGE_LABELS.get(name, name or "未知阶段")
    raw_agents = stage_agents.get(name) if isinstance(stage_agents, dict) else None
    if isinstance(raw_agents, list):
        agent = ",".join(str(item).strip() for item in raw_agents if str(item).strip()) or STAGE_AGENT_MAP.get(name, "coordinator")
    else:
        agent = STAGE_AGENT_MAP.get(name, "coordinator")
    status = str(stage.get("status") or "").strip()
    status_label = STATUS_LABELS.get(status, status or "未知")
    parts = [f"{label}: {agent} -> {status_label}"]
    parts.extend(stage_runtime_ref_parts(state, name))
    verdict = str(stage.get("verdict") or "").strip()
    if verdict:
        parts.append(f"结论={verdict}")
    score = stage.get("score")
    if score is not None:
        parts.append(f"分数={score}")
    artifact_name = stage_artifact_name(stage)
    if artifact_name:
        parts.append(f"证据={artifact_name}")
    next_action = str(stage.get("next_action") or "").strip()
    if status != "completed" and next_action:
        parts.append(f"下一步={next_action}")
    return "- " + "；".join(parts)


def render_chat_summary(
    state: dict | None,
    *,
    source: str,
    profile: str,
    returncode: int,
    raw_stdout: str = "",
    raw_stderr: str = "",
    stage_limit: int = 20,
    command_limit: int = 24,
    include_command_output: bool = False,
    show_key_artifacts: bool = False,
) -> str:
    if not state:
        tail = compact_text((raw_stderr or raw_stdout or "pipeline runner 没有返回可解析状态"), 360)
        return "\n".join(
            [
                render_progress_heading("状态", "项目任务"),
                "- 任务名称: 项目任务",
                f"- 来源: {source}/{profile}",
                f"- 回答状态: {answer_status_label('', parsed=False, returncode=returncode)}",
                f"- 状态: 无法解析 pipeline JSON，returncode={returncode}",
                f"- 输出: {tail}",
            ]
        )

    status = str(state.get("status") or "").strip()
    status_label = "已完成" if status == "completed" else "已阻塞" if status == "blocked" else status or "未知"
    stages = [item for item in state.get("stages", []) if isinstance(item, dict)]
    completed = sum(1 for item in stages if item.get("status") == "completed")
    blocked = len(stages) - completed
    task_center = state.get("task_center") if isinstance(state.get("task_center"), dict) else {}
    task_id = str(task_center.get("task_id") or "未记录").strip()
    failed_stage = str(state.get("failed_stage") or "none").strip()
    next_action = str(state.get("next_action") or "none").strip()
    run_dir = str(state.get("run_dir") or "").strip()

    title = task_title_from_state(state)
    lines = [
        render_progress_heading("状态", title),
        f"- 任务名称: {title}",
        f"- 来源: {source}/{profile}",
        f"- Run ID: {state.get('run_id', '-')}",
        f"- 回答状态: {answer_status_label(status, returncode=returncode)}",
        f"- 总状态: {status_label}",
        f"- Task Center: {task_id}",
        f"- 阶段进度: {completed}/{len(stages)} 完成，阻塞 {blocked}",
        f"- 下一步: {next_action}；失败阶段: {failed_stage}",
    ]
    if run_dir:
        lines.append(f"- 证据目录: {run_dir}")

    lines.append("")
    lines.append("## agent 分工与完成情况")
    stage_agents = state.get("stage_agents") if isinstance(state.get("stage_agents"), dict) else {}
    for stage in stages[: max(1, int(stage_limit or 20))]:
        lines.append(render_stage_line(stage, stage_agents, state))
    if len(stages) > stage_limit:
        lines.append(f"- 还有 {len(stages) - stage_limit} 个阶段未展开，详见 pipeline_state.json")

    invocations = agent_invocations(state)
    if invocations:
        lines.append("")
        lines.append("## 被调用 agent 明细")
        for item in invocations[: max(1, int(command_limit or 24))]:
            stage = str(item.get("stage") or "").strip()
            status_text = "完成" if item.get("completed") else "失败"
            parts = [
                f"{STAGE_LABELS.get(stage, stage or '阶段')}: {item.get('agent_id') or '-'}",
                f"session={item.get('session_id') or '-'}",
                f"run={item.get('run_id') or '-'}",
                f"当前阶段={STAGE_LABELS.get(stage, stage or '-')}",
                f"是否完成={status_text}",
            ]
            failure = compact_text(item.get("failure_reason") or "", 180)
            if failure:
                parts.append(f"失败原因={failure}")
            lines.append("- " + "；".join(parts))

    reports = command_reports(state)
    if reports:
        lines.append("")
        lines.append("## 阶段命令状态")
        visible_command_limit = max(1, int(command_limit or 24))
        for report in reports[:visible_command_limit]:
            lines.append(report_line(report, include_output=include_command_output))
        if len(reports) > visible_command_limit:
            lines.append(f"- 还有 {len(reports) - visible_command_limit} 条命令状态未展开，详见 command-runs/")

    auto_repair = state.get("auto_repair") if isinstance(state.get("auto_repair"), dict) else {}
    if auto_repair:
        lines.append("")
        lines.append("## 自动修复判断")
        attempts = auto_repair.get("attempts", 0)
        if attempts:
            lines.append(f"- 已自动回流 {attempts} 次，修复过程仍走 coordinator pipeline。")
        decision = compact_text(auto_repair.get("decision") or "", 240)
        if decision:
            lines.append(f"- 判断: {decision}")
        history = auto_repair.get("history") if isinstance(auto_repair.get("history"), list) else []
        for item in history[:4]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "- "
                + compact_text(
                    f"第 {item.get('attempt')} 次: {item.get('failed_stage')} -> {item.get('next_action')}；"
                    f"风险={item.get('risk')}；结果={item.get('result_status') or '已重新执行'}",
                    260,
                )
            )

    plan_excerpt = group_publish_excerpt(state, limit=1100)
    risk_summary = risk_gate_summary(state)
    if plan_excerpt:
        lines.append("")
        lines.append("## 群回传执行方案")
        if risk_summary:
            lines.append(
                "- 风险门禁: "
                + compact_text(
                    f"risk={risk_summary.get('risk_level')}; decision={risk_summary.get('execution_decision')}; "
                    f"human_confirmation_required={risk_summary.get('human_confirmation_required')}",
                    260,
                )
            )
        lines.append(f"- 摘要: {plan_excerpt}")
        lines.append("- 说明: 以上内容来自 group_plan_publish.md；如单条消息过长，应按段落拆分连续回传。")

    if status == "blocked":
        risk, reasons = classify_repair_risk(state)
        failed_stage_label = STAGE_LABELS.get(failed_stage, failed_stage or "未知阶段")
        evidence = compact_text(failure_evidence(state), 520)
        lines.append("")
        lines.append("## 阻塞原因")
        lines.append(f"- 卡点: {failed_stage_label}")
        if evidence:
            lines.append(f"- 证据: {evidence}")
        if risk == "high":
            lines.append(f"- 处理: 需要人工确认；原因={compact_text(', '.join(reasons), 240)}")
        elif next_action in REPAIRABLE_NEXT_ACTIONS:
            lines.append(f"- 处理: 可自动修复，下一轮会回流到 {next_action}。")
        else:
            lines.append(f"- 处理: 暂无自动修复路径，下一步={next_action or 'none'}。")
        failure_excerpt = group_publish_excerpt(state, failure=True, limit=1100)
        if failure_excerpt:
            lines.append("")
            lines.append("## 群回传失败摘要")
            lines.append(f"- 摘要: {failure_excerpt}")
            lines.append("- 说明: 以上内容来自 failure_summary.md，用于把具体失败内容发到群里并指导下一轮修复。")

    if show_key_artifacts:
        artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
        key_artifacts = [
            key
            for key in (
                "requirements_discussion",
                "verification",
                "code_review",
                "deployment",
                "acceptance",
                "delivery_evidence",
                "writeback",
                "git_publish",
            )
            if key in artifacts
        ]
        if key_artifacts:
            lines.append("")
            lines.append(f"关键证据: {', '.join(key_artifacts)}")
    return "\n".join(lines)


def option_value(cmd: list[str], option: str) -> str:
    try:
        index = cmd.index(option)
    except ValueError:
        return ""
    if index + 1 >= len(cmd):
        return ""
    return str(cmd[index + 1])


def run_pipeline_command(
    cmd: list[str],
    env: dict[str, str] | None = None,
    *,
    progress_interval_seconds: int = 0,
    progress_stage_limit: int = 8,
    progress_command_limit: int = 3,
    include_command_output: bool = False,
    source: str = "",
    profile: str = "",
) -> subprocess.CompletedProcess[str]:
    interval = max(0, int(progress_interval_seconds or 0))
    if interval <= 0:
        return subprocess.run(
            cmd,
            cwd=str(PROJECT_DIR),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            env=env,
        )

    run_id = option_value(cmd, "--run-id")
    requirement = option_value(cmd, "--requirement") or ""
    started_at = time.monotonic()
    if run_id:
        print(
            render_progress_start(
                run_id,
                source=source or "unknown",
                profile=profile or "unknown",
                requirement=requirement,
            ),
            flush=True,
        )
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as stdout_file, tempfile.TemporaryFile(
        mode="w+",
        encoding="utf-8",
        errors="replace",
    ) as stderr_file:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_DIR),
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        next_progress_at = started_at + interval
        while proc.poll() is None:
            now = time.monotonic()
            if run_id and now >= next_progress_at:
                state = read_json_file(run_state_path(run_id))
                progress = render_progress_update(
                    state,
                    source=source or "unknown",
                    profile=profile or "unknown",
                    elapsed_seconds=now - started_at,
                    stage_limit=progress_stage_limit,
                    command_limit=progress_command_limit,
                    include_command_output=include_command_output,
                )
                if progress:
                    print(progress, flush=True)
                next_progress_at = now + interval
            time.sleep(min(1.0, max(0.1, float(interval or 1))))
        returncode = proc.wait()
        stdout_file.seek(0)
        stderr_file.seek(0)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=int(returncode),
            stdout=stdout_file.read(),
            stderr=stderr_file.read(),
        )


def command_with_option_value(cmd: list[str], option: str, value: str) -> list[str]:
    updated = list(cmd)
    try:
        index = updated.index(option)
    except ValueError:
        updated.extend([option, value])
    else:
        if index + 1 >= len(updated):
            updated.append(value)
        else:
            updated[index + 1] = value
    return updated


def passthrough_option_value(passthrough: list[str], option: str) -> str:
    try:
        index = passthrough.index(option)
    except ValueError:
        return ""
    if index + 1 >= len(passthrough):
        return ""
    return str(passthrough[index + 1] or "")


def requirement_from_passthrough(passthrough: list[str]) -> str:
    parts: list[str] = []
    requirement = passthrough_option_value(passthrough, "--requirement")
    if requirement:
        parts.append(requirement)
    requirement_file = passthrough_option_value(passthrough, "--requirement-file")
    if requirement_file:
        path = Path(requirement_file).expanduser()
        if path.exists():
            parts.append(read_text_excerpt(path, 4000))
    return "\n\n".join(part for part in parts if part)


def normalize_code_agent(value: str | None) -> str:
    agent = str(value or "").strip()
    return agent if agent in {"backend-dev", "frontend-dev"} else ""


def infer_code_agent(requirement: str) -> str:
    text = str(requirement or "").lower()
    frontend_hit = any(keyword in text for keyword in FRONTEND_KEYWORDS)
    backend_hit = any(keyword in text for keyword in BACKEND_KEYWORDS)
    if frontend_hit and not backend_hit:
        return "frontend-dev"
    return "backend-dev"


def strip_service_control_denials(text: str) -> str:
    cleaned = text or ""
    for pattern in SERVICE_CONTROL_DENY_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned


def requirement_requests_deployment(requirement: str) -> bool:
    text = strip_service_control_denials(requirement)
    return any(pattern.search(text) for pattern in POSITIVE_DEPLOYMENT_PATTERNS)


def requirement_disables_deployment(requirement: str) -> bool:
    text = requirement or ""
    if requirement_requests_deployment(text):
        return False
    if any(pattern.search(text) for pattern in SERVICE_CONTROL_DENY_PATTERNS):
        return True
    return any(pattern.search(text) for pattern in MEMORY_DOC_ONLY_PATTERNS)


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def slugify(value: str, fallback: str = "item") -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip("-._")
    return text[:80] or fallback


def policy_dir_candidates() -> list[Path]:
    return [
        OPS_DIR / "policy",
        LOCAL_POLICY_DIR,
    ]


def policy_dir() -> Path:
    for candidate in policy_dir_candidates():
        if candidate.exists():
            return candidate
    return policy_dir_candidates()[0]


def load_task_center_classes() -> tuple[Any, Any]:
    path = policy_dir()
    if not path.exists():
        checked = ", ".join(str(candidate) for candidate in policy_dir_candidates())
        raise RuntimeError(f"Task Center policy dir not found; checked: {checked}")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    from task_center import TaskCenter, TaskCenterError  # type: ignore

    return TaskCenter, TaskCenterError


def task_executor_runner_path() -> Path:
    candidates = [
        TASK_EXECUTOR_RUNNER,
        LOCAL_POLICY_DIR / "task_executor_runner.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def resolve_agent_runner_bin(requested: str) -> str:
    value = str(requested or "").strip() or "openclaw"
    if value != "openclaw" or shutil.which(value):
        return value
    hermes_candidates = [
        RUNTIME_HOME.parent / ".local" / "bin" / "hermes",
        Path("/home/arbops/.local/bin/hermes"),
    ]
    for candidate in hermes_candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("hermes") or value


def resolve_hardflow_workflow_repo() -> Path | None:
    candidates = [
        HARDFLOW_REPO_DIR,
        Path(__file__).resolve().parents[2],
        Path("/home/arbops/projects/openclaw-hardflow-backup-20260302"),
    ]
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        marker = resolved / "skills" / "library" / "control-plane-ops" / "scripts" / "policy" / "policy_workflow.py"
        if marker.exists():
            return resolved
    return None


def specified_agent_subprocess_env(profile: str, runner_bin: str) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("OPENCLAW_HOME", str(RUNTIME_HOME))
    env.setdefault("TASK_CENTER_DIR", str(OPS_DIR / "task-center"))
    env.setdefault("OPENCLAW_POLICY_ROOT", str(OPS_DIR / "policy"))
    env.setdefault("POLICY_FILE", str(OPS_DIR / "policy" / "policy-config.json"))
    env.setdefault("POLICY_ROUTING_FILE", str(OPS_DIR / "policy" / "routing-rules.json"))
    env.setdefault("POLICY_PRICING_FILE", str(OPS_DIR / "policy" / "token-pricing.json"))
    workflow_repo = resolve_hardflow_workflow_repo()
    if workflow_repo is not None:
        env.setdefault("HARDFLOW_WORKFLOW_REPO", str(workflow_repo))
        env.setdefault("OPENCLAW_WORKFLOW_REPO", str(workflow_repo))
    if Path(str(runner_bin or "")).name.lower() in {"hermes", "hermes.exe"}:
        profile_dir = RUNTIME_HOME / "profiles" / profile
        if profile_dir.exists():
            env["HOME"] = str(RUNTIME_HOME.parent)
            env["HERMES_HOME"] = str(profile_dir)
    return env


def specified_agent_executor_command(cmd: list[str]) -> list[str]:
    target_user = specified_agent_run_as_user()
    geteuid = getattr(os, "geteuid", None)
    try:
        is_root = bool(callable(geteuid) and int(geteuid()) == 0)
    except Exception:
        is_root = False
    if is_root and target_user and shutil.which("runuser"):
        runtime_cmd = list(cmd)
        if runtime_cmd and Path(runtime_cmd[0]).name.lower().startswith("python"):
            runtime_cmd[0] = str(os.environ.get("SMART_ARB_SPECIFIED_AGENT_PYTHON", "") or "python3")
        return ["runuser", "-u", target_user, "--", *runtime_cmd]
    return cmd


def specified_agent_run_as_user() -> str:
    return str(os.environ.get("SMART_ARB_SPECIFIED_AGENT_RUN_AS", "arbops") or "").strip()


def is_effective_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    try:
        return bool(callable(geteuid) and int(geteuid()) == 0)
    except Exception:
        return False


def prepare_specified_agent_report_dir(report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    target_user = specified_agent_run_as_user()
    if not target_user or not is_effective_root() or os.name != "posix":
        return
    try:
        import pwd

        entry = pwd.getpwnam(target_user)
        uid = int(entry.pw_uid)
        gid = int(entry.pw_gid)
        for path in [report_dir, *report_dir.rglob("*")]:
            try:
                os.chown(path, uid, gid)
            except OSError:
                continue
    except Exception:
        return


def specified_agent_task_id(run_id: str, assignee: str) -> str:
    return f"specified-agent:{slugify(assignee, 'agent')}:{slugify(run_id, 'run')}"


def create_or_update_specified_agent_task(
    *,
    task_id: str,
    source: str,
    profile: str,
    assignee: str,
    requirement: str,
    run_id: str,
) -> dict[str, Any]:
    TaskCenter, TaskCenterError = load_task_center_classes()
    task_center = TaskCenter(TASK_CENTER_DB)
    payload = {
        "task_id": task_id,
        "pool": "jobs",
        "task_type": "specified_agent_dispatch",
        "reason": f"{PROJECT_KEY}: 指定 agent 执行；{compact_text(requirement, 160)}",
        "source": f"{source}:{profile}",
        "request_source": "human",
        "trace_id": run_id,
        "attempt_id": run_id,
        "priority": "medium",
        "risk_level": "low",
        "assignee": assignee,
        "status": "pending",
        "need_human_confirm": False,
        "human_confirmed": True,
        "context_payload": {
            "route_choice": "specified_agent",
            "entry_run_id": run_id,
            "source": source,
            "profile": profile,
            "project_key": PROJECT_KEY,
        },
        "requirement": requirement,
        "result_output": "由用户指定 agent 执行并返回结构化 JSON；执行器负责回写统一状态卡",
        "acceptance": "指定 agent 按用户任务返回结构化结果；执行器负责记录 session/run id 和完成/失败原因",
        "observable_outputs": "agent_task_reports,task_outputs,module_communications",
        "acceptance_thresholds": "agent_report_status=passed_or_partial,session_or_run_id_recorded",
        "required_capabilities": "specified_agent_execution,task_center_report,discord_status_card",
        "required_skills": "control-plane-ops",
        "allowed_agents": assignee,
        "workflow_profile_id": "specified_agent@discord",
        "workflow_channel": "stable",
        "selection_reason": "user_selected_specified_agent",
        "selection_inputs": {
            "selected_route": "specified_agent",
            "selected_agent": assignee,
            "entry_run_id": run_id,
        },
        "score_raw": 100,
        "score_normalized": 100,
        "score_payload": {
            "selected_route": "specified_agent",
            "assignee": assignee,
            "entry_run_id": run_id,
        },
        "action": "specified_agent_dispatch",
    }
    try:
        task_center.init_schema()
        try:
            task = task_center.get_task(task_id, display_safe=False)
        except TaskCenterError:
            task = task_center.create_task(payload, actor=f"discord:{profile}")
        else:
            task = task_center.update_task(
                task_id,
                actor=f"discord:{profile}",
                fields={key: value for key, value in payload.items() if key not in {"task_id", "pool"}},
            )
        task_center.record_module_communication(
            task_id=task_id,
            from_module=f"discord:{profile}",
            to_module=assignee,
            protocol="specified_agent_route",
            message_type="agent_dispatch",
            status="sent",
            payload_ref=run_id,
            details={
                "route_choice": "specified_agent",
                "entry_run_id": run_id,
                "assignee": assignee,
            },
            actor=f"discord:{profile}",
        )
        return task
    finally:
        task_center.close()


def task_center_snapshot(task_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    TaskCenter, _TaskCenterError = load_task_center_classes()
    task_center = TaskCenter(TASK_CENTER_DB)
    try:
        task_center.init_schema()
        task = task_center.get_task(task_id, display_safe=False)
        reports = task_center.list_agent_task_reports(task_id=task_id, limit=10, display_safe=False)
        return task, reports
    finally:
        task_center.close()


def first_executor_result(summary: dict[str, Any]) -> dict[str, Any]:
    results = summary.get("results") if isinstance(summary.get("results"), list) else []
    for item in results:
        if isinstance(item, dict):
            return item
    return {}


def report_runtime_refs(result: dict[str, Any], reports: list[dict[str, Any]]) -> dict[str, str]:
    details = {}
    if reports:
        latest = reports[0]
        details = latest.get("details") if isinstance(latest.get("details"), dict) else {}
    return {
        "executor_run_id": str(result.get("executor_run_id") or result.get("run_id") or details.get("run_id") or "").strip(),
        "session_id": str(result.get("session_id") or details.get("session_id") or "").strip(),
        "agent_run_id": str(result.get("agent_run_id") or details.get("agent_run_id") or "").strip(),
        "agent_session_key": str(result.get("agent_session_key") or details.get("agent_session_key") or "").strip(),
        "agent_runtime_session_id": str(result.get("agent_runtime_session_id") or details.get("agent_runtime_session_id") or "").strip(),
    }


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "passed", "ok"}


def latest_report(reports: list[dict[str, Any]]) -> dict[str, Any]:
    return reports[0] if reports and isinstance(reports[0], dict) else {}


def specified_agent_report_status(result: dict[str, Any], reports: list[dict[str, Any]]) -> str:
    report = latest_report(reports)
    explicit = str(result.get("report_status") or "").strip().lower()
    if explicit:
        return explicit
    reported = str(report.get("status") or "").strip().lower()
    if reported:
        return reported
    status = str(result.get("status") or "").strip().lower()
    return status if status in {"passed", "partial", "failed", "escalated"} else ""


def specified_agent_solved(result: dict[str, Any], reports: list[dict[str, Any]]) -> bool:
    if "solved" in result:
        return truthy(result.get("solved"))
    report = latest_report(reports)
    return truthy(report.get("solved"))


def specified_agent_failure_reason(result: dict[str, Any], reports: list[dict[str, Any]], stderr: str = "") -> str:
    failed_items = result.get("failed_items") if isinstance(result.get("failed_items"), list) else []
    parts = [
        str(result.get("reason") or "").strip(),
        ",".join(str(item).strip() for item in failed_items if str(item).strip()),
        str(result.get("resolution_summary") or "").strip(),
        str(stderr or "").strip(),
    ]
    if reports:
        latest = reports[0]
        parts.extend(
            [
                ",".join(str(item).strip() for item in latest.get("failed_items", []) if str(item).strip()),
                str(latest.get("resolution_summary") or "").strip(),
            ]
        )
    return compact_text("; ".join(part for part in parts if part), 260) or "none"


def render_specified_agent_card(payload: dict[str, Any]) -> str:
    refs = payload.get("refs") if isinstance(payload.get("refs"), dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    reports = payload.get("reports") if isinstance(payload.get("reports"), list) else []
    report_status = specified_agent_report_status(result, reports)
    stage = str(result.get("stage") or task.get("stage_id") or "dispatch").strip()
    completed = bool(payload.get("completed"))
    lines = [
        "# nofx 指定 agent 执行状态",
        f"来源: {payload.get('source', '-')}/{payload.get('profile', '-')}",
        "路线: specified_agent",
        f"Task Center: {payload.get('task_id', '-')}",
        f"被调用 agent: {payload.get('assignee', '-')}",
        f"agent runner: {payload.get('agent_runner_bin') or '-'}",
        f"executor run id: {refs.get('executor_run_id') or '-'}",
        f"agent session id: {refs.get('session_id') or refs.get('agent_runtime_session_id') or '-'}",
        f"agent run id: {refs.get('agent_run_id') or '-'}",
        f"session key: {refs.get('agent_session_key') or '-'}",
        f"当前阶段: {stage}",
        f"是否完成: {'是' if completed else '否'}",
        f"总状态: task={task.get('status') or '-'}；report={report_status or '-'}",
        f"失败原因: {payload.get('failure_reason') or 'none'}",
        f"回答状态: {'已回答完毕' if completed else '未回答完毕，指定 agent 未通过或执行失败'}",
    ]
    return "\n".join(lines)


def render_specified_agent_assignee_required_card(*, source: str, profile: str, requirement: str) -> str:
    recommended_route, reason = recommend_discord_route(requirement)
    return "\n".join(
        [
            "# nofx 指定 agent 执行状态",
            f"来源: {source}/{profile}",
            "路线: specified_agent",
            "总状态: 等待指定 agent",
            f"推荐链路: {recommended_route}",
            f"推荐原因: {reason}",
            "下一步: 请补充 agent id，例如 project-agent、reviewer、backend-dev、frontend-dev、tester、deployer、doc-writer。",
            "回答状态: 等待人工选择 agent",
        ]
    )


def run_specified_agent_route(args: argparse.Namespace, requirement: str, profile: str) -> dict[str, Any]:
    assignee = str(args.assignee or "").strip()
    if not assignee:
        return {
            "status": "blocked",
            "next_action": "await_specified_agent_assignee",
            "source": args.source,
            "profile": profile,
            "route_choice": "specified_agent",
            "completed": False,
            "failure_reason": "missing_assignee",
        }

    run_id = utc_run_id(f"{args.source}-{profile}-specified-{assignee}")
    task_id = specified_agent_task_id(run_id, assignee)
    task = create_or_update_specified_agent_task(
        task_id=task_id,
        source=args.source,
        profile=profile,
        assignee=assignee,
        requirement=requirement,
        run_id=run_id,
    )
    runner = task_executor_runner_path()
    agent_runner_bin = resolve_agent_runner_bin(str(args.openclaw_bin))
    report_dir = OPS_DIR / "task-executor-runs"
    prepare_specified_agent_report_dir(report_dir)
    cmd = [
        sys.executable,
        str(runner),
        "--db",
        str(TASK_CENTER_DB),
        "--only-task-id",
        task_id,
        "--max-tasks",
        "1",
        "--actor",
        f"discord:{profile}",
        "--planner-id",
        profile,
        "--openclaw-bin",
        agent_runner_bin,
        "--timeout-sec",
        str(max(30, int(args.specified_agent_timeout_seconds or 1200))),
        "--report-dir",
        str(report_dir),
        "--emit-json",
    ]
    proc = subprocess.run(
        specified_agent_executor_command(cmd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        cwd=str(PROJECT_DIR) if PROJECT_DIR.exists() else None,
        env=specified_agent_subprocess_env(profile, agent_runner_bin),
        timeout=max(60, int(args.specified_agent_timeout_seconds or 1200) + 120),
        check=False,
    )
    summary = parse_json_payload(proc.stdout)
    result = first_executor_result(summary)
    task_snapshot, reports = task_center_snapshot(task_id)
    refs = report_runtime_refs(result, reports)
    report_status = specified_agent_report_status(result, reports)
    completed = (
        int(proc.returncode or 0) == 0
        and str(task_snapshot.get("status") or "").strip().lower() == "passed"
        and report_status in {"passed", "partial"}
        and (report_status == "passed" or specified_agent_solved(result, reports))
    )
    failure_reason = "none" if completed else specified_agent_failure_reason(result, reports, proc.stderr)
    return {
        "status": "completed" if completed else "blocked",
        "next_action": "none" if completed else "inspect_specified_agent_result",
        "source": args.source,
        "profile": profile,
        "route_choice": "specified_agent",
        "run_id": run_id,
        "task_id": task_id,
        "assignee": assignee,
        "agent_runner_bin": agent_runner_bin,
        "task": task_snapshot,
        "reports": reports,
        "created_task": task,
        "executor_summary": summary,
        "result": result,
        "refs": refs,
        "completed": completed,
        "returncode": int(proc.returncode or 0),
        "failure_reason": failure_reason,
        "stderr": compact_text(proc.stderr, 600),
    }


def bridge_command(stage: str, args: argparse.Namespace, reviewer_role: str | None = None) -> str:
    provider = args.live_bridge_provider
    model = args.live_bridge_model
    if reviewer_role == "reviewer-a":
        provider = args.reviewer_a_provider or provider
        model = args.reviewer_a_model or model
    elif reviewer_role == "reviewer-b":
        provider = args.reviewer_b_provider or provider
        model = args.reviewer_b_model or model
    command = [
        sys.executable,
        str(BRIDGE),
        "--stage",
        stage,
        "--profile",
        args.profile,
        "--agent-mode",
        args.live_bridge_agent_mode,
        "--provider",
        provider,
        "--model",
        model,
    ]
    if reviewer_role:
        command.extend(["--reviewer-role", reviewer_role])
    if stage in {"requirements_review", "solution_review", "code_review"} and args.reviewer_fallback_models:
        command.extend(["--reviewer-fallback-models", args.reviewer_fallback_models])
    if stage == "code_execution" and not args.live_bridge_no_yolo:
        command.append("--allow-yolo")
        command.extend(["--max-turns", str(args.live_bridge_code_max_turns)])
    elif stage in {"external_research", "requirements_discussion", "requirements_review", "solution_review", "code_review"}:
        command.extend(["--max-turns", str(args.live_bridge_agent_max_turns)])
    elif stage == "verification":
        command.extend(
            [
                "--verification-command-timeout-seconds",
                str(args.live_bridge_verification_command_timeout_seconds),
            ]
        )
    if stage == "deployment" and not args.no_internal_api_restart:
        command.append("--allow-internal-api-restart")
    return " ".join(shlex.quote(str(part)) for part in command)


def default_live_bridge_args(args: argparse.Namespace, passthrough: list[str]) -> list[str]:
    if not args.live or args.no_live_bridge:
        return []

    injected: list[str] = []
    inject_deployment = not args.skip_deployment_command and not requirement_disables_deployment(
        requirement_from_passthrough(passthrough)
    )
    command_options = [
        ("--research-command", "external_research"),
        ("--requirements-discussion-command", "requirements_discussion"),
        ("--code-command", "code_execution"),
        ("--verification-command", "verification"),
        ("--memory-write-command", "memory_writeback"),
    ]
    review_command_options = [
        ("--requirements-review-command", "requirements_review", "reviewer-a"),
        ("--requirements-review-command", "requirements_review", "reviewer-b"),
        ("--solution-review-command", "solution_review", "reviewer-a"),
        ("--solution-review-command", "solution_review", "reviewer-b"),
        ("--code-review-command", "code_review", "reviewer-a"),
        ("--code-review-command", "code_review", "reviewer-b"),
    ]
    if inject_deployment:
        command_options.insert(5, ("--deployment-command", "deployment"))
    if not args.skip_git_publish_command:
        command_options.append(("--git-publish-command", "git_publish"))
    for option, stage in command_options:
        if not option_present(passthrough, option):
            injected.extend([option, bridge_command(stage, args)])
    for option, stage, reviewer_role in review_command_options:
        if not option_present(passthrough, option):
            injected.extend([option, bridge_command(stage, args, reviewer_role=reviewer_role)])
    if not option_present(passthrough, "--command-timeout-seconds"):
        injected.extend(["--command-timeout-seconds", str(args.live_bridge_timeout_seconds)])
    return injected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smart arbitrage project delivery pipeline entry")
    parser.add_argument("--source", default="discord")
    parser.add_argument("--profile", default=os.environ.get("SMART_ARB_LIVE_BRIDGE_PROFILE", "arbitrageagent"))
    parser.add_argument(
        "--route-choice",
        choices=sorted(VALID_ROUTE_CHOICES),
        default=os.environ.get("SMART_ARB_ROUTE_CHOICE", ""),
        help="manual route selected by the Discord user; Discord pipeline execution requires a pipeline route",
    )
    parser.add_argument("--assignee", default=os.environ.get("SMART_ARB_SPECIFIED_AGENT", ""), help="agent id used by the specified_agent route")
    parser.add_argument("--openclaw-bin", default=os.environ.get("SMART_ARB_OPENCLAW_BIN", "openclaw"), help="OpenClaw binary used by task_executor_runner for specified_agent dispatch")
    parser.add_argument(
        "--specified-agent-timeout-seconds",
        type=int,
        default=int(os.environ.get("SMART_ARB_SPECIFIED_AGENT_TIMEOUT_SECONDS", "1200")),
        help="timeout for the specified_agent Task Center executor",
    )
    parser.add_argument("--live", action="store_true", help="kept for compatibility; this entrypoint always runs live")
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--requirement", default="", help="task requirement passed through to the pipeline runner")
    parser.add_argument("--requirement-file", default="", help="file containing the task requirement passed through to the pipeline runner")
    parser.add_argument("--no-live-bridge", action="store_true", help="do not inject default live evidence commands")
    parser.add_argument("--live-bridge-agent-mode", choices=["hermes", "echo"], default=os.environ.get("SMART_ARB_LIVE_BRIDGE_AGENT_MODE", "hermes"))
    parser.add_argument("--live-bridge-provider", default=os.environ.get("SMART_ARB_LIVE_BRIDGE_PROVIDER", "openai-codex"))
    parser.add_argument("--live-bridge-model", default=os.environ.get("SMART_ARB_LIVE_BRIDGE_MODEL", "gpt-5.5"))
    parser.add_argument("--reviewer-a-provider", default=os.environ.get("SMART_ARB_REVIEWER_A_PROVIDER"))
    parser.add_argument("--reviewer-a-model", default=os.environ.get("SMART_ARB_REVIEWER_A_MODEL"))
    parser.add_argument("--reviewer-b-provider", default=os.environ.get("SMART_ARB_REVIEWER_B_PROVIDER") or DEFAULT_REVIEWER_B_PROVIDER)
    parser.add_argument("--reviewer-b-model", default=os.environ.get("SMART_ARB_REVIEWER_B_MODEL") or DEFAULT_REVIEWER_B_MODEL)
    parser.add_argument("--reviewer-fallback-models", default=os.environ.get("SMART_ARB_REVIEWER_FALLBACK_MODELS") or DEFAULT_REVIEWER_FALLBACK_MODELS)
    parser.add_argument("--live-bridge-timeout-seconds", type=int, default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_TIMEOUT_SECONDS", "1800")))
    parser.add_argument(
        "--live-bridge-verification-command-timeout-seconds",
        type=int,
        default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_VERIFICATION_COMMAND_TIMEOUT_SECONDS", "300")),
        help="per-command timeout used inside the live verification bridge",
    )
    parser.add_argument("--live-bridge-agent-max-turns", type=int, default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_AGENT_MAX_TURNS", "24")))
    parser.add_argument("--live-bridge-code-max-turns", type=int, default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_CODE_MAX_TURNS", "60")))
    parser.add_argument("--code-agent", choices=["backend-dev", "frontend-dev"], default=normalize_code_agent(os.environ.get("SMART_ARB_CODE_AGENT", "")), help="workflow owner for code execution; defaults to inferred backend/frontend owner")
    parser.add_argument("--live-bridge-no-yolo", action="store_true", help="do not let Hermes bypass command approvals for code execution")
    parser.add_argument("--no-internal-api-restart", action="store_true", help="do not restart the internal FastAPI tmux service in deployment stage")
    parser.add_argument("--skip-deployment-command", action="store_true", help="do not inject the deployment stage live bridge command")
    parser.add_argument(
        "--skip-git-publish-command",
        action="store_true",
        default=env_flag("SMART_ARB_SKIP_GIT_PUBLISH_COMMAND", False),
        help="do not inject the gated git publish stage",
    )
    parser.add_argument("--emit-json", action="store_true", help="print raw pipeline JSON instead of the chat summary")
    parser.add_argument("--no-chat-summary", action="store_true", help="print raw runner output without the chat summary")
    parser.add_argument("--chat-stage-limit", type=int, default=int(os.environ.get("SMART_ARB_CHAT_STAGE_LIMIT", "20")))
    parser.add_argument("--chat-command-limit", type=int, default=int(os.environ.get("SMART_ARB_CHAT_COMMAND_LIMIT", "24")))
    parser.add_argument(
        "--chat-include-command-output",
        action="store_true",
        default=env_flag("SMART_ARB_CHAT_INCLUDE_COMMAND_OUTPUT", False),
        help="include compact command stdout/stderr excerpts in chat cards; disabled by default",
    )
    parser.add_argument(
        "--chat-show-key-artifacts",
        action="store_true",
        default=env_flag("SMART_ARB_CHAT_SHOW_KEY_ARTIFACTS", False),
        help="append the legacy key artifact name list to the final chat card",
    )
    parser.add_argument(
        "--progress-interval-seconds",
        type=int,
        default=int(os.environ.get("SMART_ARB_PROGRESS_INTERVAL_SECONDS", "60")),
        help="print an in-flight progress card every N seconds; set to 0 to disable",
    )
    parser.add_argument(
        "--progress-stage-limit",
        type=int,
        default=int(os.environ.get("SMART_ARB_PROGRESS_STAGE_LIMIT", "8")),
        help="number of recent stages to include in in-flight progress cards",
    )
    parser.add_argument(
        "--progress-command-limit",
        type=int,
        default=int(os.environ.get("SMART_ARB_PROGRESS_COMMAND_LIMIT", "3")),
        help="number of recent command outputs to include in in-flight progress cards",
    )
    parser.add_argument(
        "--auto-repair-attempts",
        type=int,
        default=int(os.environ.get("SMART_ARB_AUTO_REPAIR_ATTEMPTS", "4")),
        help="retry repairable blocked live runs through the same pipeline",
    )
    parser.add_argument("--no-auto-repair", action="store_true", help="disable automatic pipeline repair loops")
    parser.add_argument(
        "--human-risk-confirmed",
        action="store_true",
        default=env_flag("SMART_ARB_HUMAN_RISK_CONFIRMED", False),
        help="carry audited human approval through the pre-execution high-risk gate",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, passthrough = parser.parse_known_args(argv)
    if args.dry_run or option_present(passthrough, "--dry-run"):
        parser.error("dry-run is disabled for smart-arb-pipeline; execution requests always run live")
    args.live = True

    profile = args.profile or "arbitrageagent"
    requirement_passthrough: list[str] = []
    if str(getattr(args, "requirement", "") or "").strip():
        requirement_passthrough += ["--requirement", str(args.requirement)]
    if str(getattr(args, "requirement_file", "") or "").strip():
        requirement_passthrough += ["--requirement-file", str(args.requirement_file)]
    requirement_text = requirement_from_passthrough([*passthrough, *requirement_passthrough])
    route_choice = normalize_route_choice(args.route_choice)
    if should_block_for_discord_route_choice(args.source, route_choice):
        payload = route_selection_payload(source=args.source, profile=profile, requirement=requirement_text)
        if route_choice in NON_PIPELINE_ROUTE_CHOICES:
            payload["selected_route"] = route_choice
            payload["status"] = "skipped"
            payload["next_action"] = f"manual_route_not_pipeline:{route_choice}"
        if args.emit_json or args.no_chat_summary:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(render_route_selection_card(source=args.source, profile=profile, requirement=requirement_text))
        return 0

    if route_choice == "specified_agent":
        payload = run_specified_agent_route(args, requirement_text, profile)
        if args.emit_json or args.no_chat_summary:
            print(json.dumps(payload, ensure_ascii=False))
        elif not str(args.assignee or "").strip():
            print(render_specified_agent_assignee_required_card(source=args.source, profile=profile, requirement=requirement_text))
        else:
            print(render_specified_agent_card(payload))
        return int(payload.get("returncode") or 0)

    run_id = utc_run_id(f"{args.source}-{profile}")
    cmd = [
        sys.executable,
        str(RUNNER),
        "--project-key",
        PROJECT_KEY,
        "--runtime-host",
        "hermes",
        "--runtime-home",
        str(RUNTIME_HOME),
        "--workspace-root",
        str(WORKSPACE_ROOT),
        "--project-memory-root",
        str(PROJECT_MEMORY_ROOT),
        "--command-cwd",
        str(PROJECT_DIR),
        "--record-task-center",
        "--task-center-db",
        str(TASK_CENTER_DB),
        "--write-project-memory",
        "--run-id",
        run_id,
        "--source-url",
        f"{args.source}:{profile}",
        "--force",
        "--emit-json",
    ]
    if args.human_risk_confirmed:
        cmd.append("--human-risk-confirmed")
    code_agent = normalize_code_agent(args.code_agent) or infer_code_agent(requirement_text)
    cmd += ["--code-agent", code_agent]
    cmd += default_live_bridge_args(args, [*passthrough, *requirement_passthrough])
    cmd += passthrough
    cmd += requirement_passthrough
    progress_interval_seconds = 0 if args.emit_json or args.no_chat_summary else int(args.progress_interval_seconds or 0)
    progress_kwargs = {
        "progress_interval_seconds": progress_interval_seconds,
        "progress_stage_limit": int(args.progress_stage_limit or 0),
        "progress_command_limit": int(args.progress_command_limit or 0),
        "include_command_output": bool(args.chat_include_command_output),
        "source": args.source,
        "profile": profile,
    }
    proc = run_pipeline_command(cmd, **progress_kwargs)
    state = parse_runner_state(proc.stdout)
    repair_history: list[dict[str, object]] = []
    repair_attempts = 0
    max_repair_attempts = 0 if args.no_auto_repair else max(0, int(args.auto_repair_attempts or 0))
    repair_env = dict(os.environ)

    while state:
        do_repair, risk, reasons = should_auto_repair(state, repair_attempts, max_repair_attempts)
        if not do_repair:
            if str(state.get("status") or "") == "blocked":
                state["auto_repair"] = {
                    "attempts": repair_attempts,
                    "decision": compact_text(f"未继续自动修复: {risk}; {', '.join(reasons)}", 360),
                    "history": repair_history,
                }
            break
        repair_attempts += 1
        repair_env.pop("SMART_ARB_ENTRY_REPAIR_CONTEXT_FILE", None)
        repair_env.pop("PIPELINE_REPAIR_CONTEXT_FILE", None)
        context_text = repair_context_markdown(state, repair_attempts, risk, reasons)
        context_file = write_repair_context_file(state, repair_attempts, risk, reasons, context_text)
        repair_run_id = f"{run_id}-repair{repair_attempts}"
        repair_cmd = command_with_option_value(cmd, "--run-id", repair_run_id)
        repair_env["PIPELINE_REPAIR_CONTEXT"] = context_text
        repair_env["SMART_ARB_ENTRY_REPAIR_CONTEXT"] = context_text
        repair_env["PIPELINE_REPAIR_ATTEMPT"] = str(repair_attempts)
        if context_file is not None:
            repair_env["SMART_ARB_ENTRY_REPAIR_CONTEXT_FILE"] = str(context_file)
            repair_env["PIPELINE_REPAIR_CONTEXT_FILE"] = str(context_file)
        repair_item: dict[str, object] = {
            "attempt": repair_attempts,
            "run_id": repair_run_id,
            "failed_stage": state.get("failed_stage"),
            "next_action": state.get("next_action"),
            "risk": risk,
            "reason": ", ".join(reasons),
            "context_file": str(context_file or ""),
            "context_delivery": "file+env" if context_file is not None else "env",
        }
        proc = run_pipeline_command(repair_cmd, env=repair_env, **progress_kwargs)
        next_state = parse_runner_state(proc.stdout)
        repair_item["returncode"] = int(proc.returncode)
        repair_item["result_status"] = next_state.get("status") if isinstance(next_state, dict) else "unparsed"
        repair_history.append(repair_item)
        if not next_state:
            break
        state = next_state

    if state and repair_history:
        state["auto_repair"] = {
            "attempts": repair_attempts,
            "decision": (
                "自动修复后通过"
                if state.get("status") == "completed"
                else compact_text(f"自动修复后仍未通过: {state.get('status')} / {state.get('failed_stage')}", 360)
            ),
            "history": repair_history,
        }

    if args.emit_json or args.no_chat_summary:
        if args.emit_json and state and repair_history:
            print(json.dumps(state, ensure_ascii=False))
        elif proc.stdout:
            print(proc.stdout.rstrip())
        if proc.stderr:
            print(proc.stderr.rstrip(), file=sys.stderr)
    else:
        print(
            render_chat_summary(
                state,
                source=args.source,
                profile=profile,
                returncode=int(proc.returncode),
                raw_stdout=proc.stdout,
                raw_stderr=proc.stderr,
                stage_limit=args.chat_stage_limit,
                command_limit=args.chat_command_limit,
                include_command_output=bool(args.chat_include_command_output),
                show_key_artifacts=bool(args.chat_show_key_artifacts),
            )
        )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
