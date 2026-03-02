#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
问题分析引擎

分析测试结果，分类问题，识别复杂问题
"""

import json
from pathlib import Path


class Problem:
    """问题类"""

    def __init__(self, category, title, description, severity="medium", details=None):
        self.category = category  # config/database/api/auth/frontend
        self.title = title
        self.description = description
        self.severity = severity  # simple/medium/complex
        self.details = details or {}
        self.fix_strategy = None

    def __repr__(self):
        return f"<Problem({self.category}: {self.title})>"


class ProblemAnalyzer:
    """问题分析器"""

    def __init__(self, config):
        self.config = config

    def analyze(self, test_results):
        """
        分析测试结果，分类问题

        Args:
            test_results: 测试结果字典

        Returns:
            问题列表，按优先级排序
        """
        problems = []

        # 1. 解析测试报告
        report_data = self._parse_test_report()

        if not report_data:
            print("⚠️  无法解析测试报告")
            return problems

        # 2. 分类问题
        problems.extend(self._analyze_port_failures(report_data))
        problems.extend(self._analyze_api_failures(report_data))
        problems.extend(self._analyze_ui_failures(report_data))

        # 3. 按优先级排序
        problems = self._sort_by_priority(problems)

        return problems

    def _parse_test_report(self):
        """解析测试报告"""
        report_dir = Path(self.config["test"]["reportDir"])

        if not report_dir.exists():
            return None

        # 查找最新的测试报告
        report_files = list(report_dir.glob("deployment-test-report-*.md"))

        if not report_files:
            return None

        # 获取最新的报告
        latest_report = max(report_files, key=lambda p: p.stat().st_mtime)

        # 解析报告内容
        with open(latest_report, 'r', encoding='utf-8') as f:
            content = f.read()

        # TODO: 解析 Markdown 格式的测试报告
        # 提取失败信息
        return {"content": content, "path": str(latest_report)}

    def _analyze_port_failures(self, report_data):
        """分析端口失败"""
        problems = []
        content = report_data.get("content", "")

        # 查找端口失败信息
        # 示例: "MySQL (127.0.0.1:3306)... ❌ 未监听"
        import re

        # 查找所有失败的端口
        failed_ports = re.findall(r'(\w+)\s*\([^)]+\)\.\.\. (❌ 未监听|未监听)', content)

        for service, status in failed_ports:
            problem = Problem(
                category="config",
                title=f"{service} 端口未监听",
                description=f"{service} 服务端口未监听",
                severity="simple",
                details={"service": service, "status": status}
            )
            problems.append(problem)

        return problems

    def _analyze_api_failures(self, report_data):
        """分析 API 失败"""
        problems = []
        content = report_data.get("content", "")

        import re

        # 查找 API 失败信息
        # 示例: "❌ /api/pm-robot/create: 状态码: 预期 200, 实际 404"
        api_failures = re.findall(
            r'❌\s+(.+?):\s+(.+)',
            content
        )

        for failure_info in api_failures:
            # 解析失败信息
            if "状态码" in failure_info or "404" in failure_info:
                problem = Problem(
                    category="api",
                    title=f"API 接口失败: {failure_info.split(':')[0] if ':' in failure_info else failure_info}",
                    description=failure_info,
                    severity="medium",
                    details={"raw": failure_info}
                )
                problems.append(problem)

        return problems

    def _analyze_ui_failures(self, report_data):
        """分析 UI 失败"""
        problems = []
        content = report_data.get("content", "")

        import re

        # 查找 UI 失败信息
        ui_failures = re.findall(
            r'❌\s+(.+?):\s+(.+)',
            content
        )

        for failure_info in ui_failures:
            if "元素" in failure_info or "组件" in failure_info or "渲染" in failure_info:
                problem = Problem(
                    category="frontend",
                    title=f"UI 失败: {failure_info}",
                    description=failure_info,
                    severity="medium",
                    details={"raw": failure_info}
                )
                problems.append(problem)

        return problems

    def _sort_by_priority(self, problems):
        """按优先级排序问题"""
        priority_order = {
            "config": 0,
            "database": 1,
            "api": 2,
            "auth": 3,
            "frontend": 4
        }

        return sorted(
            problems,
            key=lambda p: priority_order.get(p.category, 99)
        )

    def classify_severity(self, problem):
        """
        分类问题严重级别

        Returns:
            'simple' / 'medium' / 'complex'
        """
        # 简单问题：配置错误、端口问题
        if problem.category == "config":
            return "simple"

        # 中等问题：API 404、字段缺失
        if problem.category in ["api", "frontend"]:
            if "404" in problem.description or "缺失" in problem.description:
                return "medium"

        # 复杂问题：数据库迁移、权限问题
        if "迁移" in problem.description or "权限" in problem.description:
            return "complex"

        return "medium"

    def detect_complex_problem(self, problem):
        """
        检测是否为复杂问题

        Returns:
            True/False
        """
        complex_keywords = [
            "架构", "重构", "业务逻辑", "性能",
            "循环依赖", "数据模型", "权限设计"
        ]

        for keyword in complex_keywords:
            if keyword in problem.description:
                return True

        return False
