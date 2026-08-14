#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能路由引擎 - 支持显式调用
"""
import re
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

class ExplicitCallDetector:
    """显式调用检测器"""

    def __init__(self, config_path: str, *, skills_dir: str, agent_names: set[str]):
        """初始化检测器

        Args:
            config_path: intent_patterns.json 配置文件路径
        """
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.patterns = self.config['explicit_call_patterns']
        self.extraction_rules = self.config['task_extraction']
        self.fallback_behavior = self.config['fallback_behavior']
        self.validation_rules = self.config['validation']
        self.case_sensitive = bool(self.validation_rules.get('case_sensitive', False))
        self.skills_dir = Path(skills_dir).expanduser().resolve()
        self.skill_names = {
            child.name if self.case_sensitive else child.name.casefold()
            for child in self.skills_dir.iterdir()
            if child.is_dir() and (child / 'SKILL.md').is_file()
        } if self.skills_dir.is_dir() else set()
        self.agent_names = {
            name if self.case_sensitive else name.casefold()
            for name in agent_names
        }
        self.combo_targets: dict[str, list[str]] = {}
        configured_combos = self.validation_rules.get('combos', {})
        for combo_name, members in configured_combos.items():
            normalized_combo = combo_name if self.case_sensitive else combo_name.casefold()
            normalized_members = {
                member if self.case_sensitive else member.casefold()
                for member in members
            }
            if members and normalized_members.issubset(self.agent_names):
                self.combo_targets[normalized_combo] = list(members)
        self.combo_names = set(self.combo_targets)

    def detect_explicit_call(self, user_input: str) -> Optional[Dict[str, Any]]:
        """检测显式调用

        Args:
            user_input: 用户输入

        Returns:
            如果检测到显式调用，返回调用信息字典：
            {
                'type': 'skill' | 'subagent' | 'combo',
                'name': 'pdf',
                'task': '提取表格数据',
                'raw_match': '...'
            }
            如果未检测到，返回 None
        """
        for pattern_config in self.patterns:
            pattern = pattern_config['pattern']
            match = re.search(pattern, user_input)

            if match:
                call_type = pattern_config['type']
                target_name = match.group(1).strip()
                task_description = match.group(2).strip() if len(match.groups()) > 1 else ""

                # 如果任务描述为空，使用回退规则
                if not task_description:
                    task_description = self._extract_task_fallback(user_input, match)

                return {
                    'type': call_type,
                    'name': target_name,
                    'task': task_description,
                    'raw_match': match.group(0),
                    'priority': pattern_config['priority']
                }

        return None

    def _extract_task_fallback(self, user_input: str, match: re.Match) -> str:
        """回退规则：提取任务描述

        Args:
            user_input: 完整用户输入
            match: 正则匹配对象

        Returns:
            提取的任务描述
        """
        # 获取匹配位置之后的内容
        after_match = user_input[match.end():].strip()

        if after_match:
            return after_match[:self.extraction_rules['max_length']]

        # 如果仍然为空，使用完整用户输入
        if self.fallback_behavior['empty_task'] == 'use_full_user_input':
            return user_input[:self.extraction_rules['max_length']]

        return "执行任务"

    def validate_target(self, call_type: str, target_name: str) -> bool:
        """验证目标是否存在

        Args:
            call_type: 调用类型
            target_name: 目标名称

        Returns:
            是否有效
        """
        rule_names = {
            'skill': 'check_skill_exists',
            'subagent': 'check_subagent_exists',
            'combo': 'check_combo_exists',
        }
        rule_name = rule_names.get(call_type)
        if rule_name is None:
            return False
        if not self.validation_rules.get(rule_name, True):
            return True

        normalized = target_name.strip().rsplit(':', 1)[-1]
        if not self.case_sensitive:
            normalized = normalized.casefold()
        if call_type == 'skill':
            return normalized in self.skill_names
        if call_type == 'subagent':
            return normalized in self.agent_names
        return normalized in self.combo_names

    def resolve_combo(self, target_name: str) -> list[str]:
        normalized = target_name.strip()
        if not self.case_sensitive:
            normalized = normalized.casefold()
        return list(self.combo_targets.get(normalized, []))


class IntelligentRouter:
    """智能路由引擎"""

    def __init__(self, skills_dir: str, config_dir: str, agents_dir: Optional[str] = None):
        """初始化路由引擎

        Args:
            skills_dir: 技能目录
            config_dir: 配置目录
            agents_dir: 目标 Runtime 的 Agent 能力目录
        """
        self.skills_dir = str(Path(skills_dir).expanduser().resolve())
        self.config_dir = str(Path(config_dir).expanduser().resolve())
        self.agents_dir = self._resolve_agents_dir(agents_dir)

        with open(os.path.join(self.config_dir, 'agent_registry.json'), 'r', encoding='utf-8') as f:
            agent_registry = json.load(f)
        self.declared_agent_names = {
            item['name']
            for item in agent_registry.get('agents', [])
            if item.get('available', True) and item.get('name')
        }
        self.discovered_agent_names = self._discover_agent_names(self.agents_dir)
        self.agent_names = self.declared_agent_names & self.discovered_agent_names
        self.registry_missing_agents = self.declared_agent_names - self.discovered_agent_names
        self.unregistered_agents = self.discovered_agent_names - self.declared_agent_names
        self.skill_names = {
            child.name.casefold()
            for child in Path(self.skills_dir).iterdir()
            if child.is_dir() and (child / 'SKILL.md').is_file()
        } if Path(self.skills_dir).is_dir() else set()
        self.known_targets = self.skill_names | {name.casefold() for name in self.agent_names}

        # 加载配置
        self.explicit_detector = ExplicitCallDetector(
            os.path.join(self.config_dir, 'intent_patterns.json'),
            skills_dir=self.skills_dir,
            agent_names=self.agent_names,
        )

        with open(os.path.join(self.config_dir, 'keyword_routes.json'), 'r', encoding='utf-8') as f:
            self.keyword_routes = json.load(f)

        with open(os.path.join(self.config_dir, 'file_type_routes.json'), 'r', encoding='utf-8') as f:
            self.file_type_routes = json.load(f)

    def _resolve_agents_dir(self, agents_dir: Optional[str]) -> Optional[Path]:
        if agents_dir:
            resolved = Path(agents_dir).expanduser().resolve()
            return resolved if resolved.is_dir() else None
        env_agents_dir = os.environ.get('HARDFLOW_AGENTS_DIR')
        if env_agents_dir:
            resolved = Path(env_agents_dir).expanduser().resolve()
            return resolved if resolved.is_dir() else None
        candidates: list[Path] = []
        for parent in Path(self.config_dir).parents:
            candidates.append(parent / 'agents')
        for candidate in candidates:
            resolved = candidate.expanduser().resolve()
            if resolved.is_dir():
                return resolved
        return None

    @staticmethod
    def _discover_agent_names(agents_dir: Optional[Path]) -> set[str]:
        if agents_dir is None:
            return set()
        marker_names = {'SOUL.md', 'AGENT.md', 'agent.json'}
        return {
            child.name
            for child in agents_dir.iterdir()
            if child.is_dir() and any((child / marker).is_file() for marker in marker_names)
        }

    def _is_known_target(self, target_name: Optional[str]) -> bool:
        if not target_name:
            return False
        normalized = target_name.strip().rsplit(':', 1)[-1].casefold()
        return normalized in self.known_targets

    @staticmethod
    def _ordered_routes(routes: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        """按显式优先级排序，并在优先级相同时保留配置顺序。"""
        return [
            route
            for _, route in sorted(
                enumerate(routes),
                key=lambda item: (item[1].get('priority', 10), item[0]),
            )
        ]

    def route(self, user_input: str, file_context: Optional[str] = None) -> Dict[str, Any]:
        """路由决策

        Args:
            user_input: 用户输入
            file_context: 当前编辑的文件类型（可选）

        Returns:
            路由决策结果：
            {
                'method': 'explicit' | 'keyword' | 'file_type' | 'default',
                'target': '目标技能/Agent',
                'task': '任务描述',
                'confidence': 0.95
            }
        """
        # 优先级 1: 显式调用检测
        explicit_call = self.explicit_detector.detect_explicit_call(user_input)
        if explicit_call and self.explicit_detector.validate_target(
            explicit_call['type'], explicit_call['name']
        ):
            decision = {
                'method': 'explicit',
                'target': explicit_call['name'],
                'task': explicit_call['task'],
                'type': explicit_call['type'],
                'confidence': 1.0,
                'raw_match': explicit_call['raw_match']
            }
            if explicit_call['type'] == 'combo':
                decision['targets'] = self.explicit_detector.resolve_combo(explicit_call['name'])
            return decision

        # 优先级 2: 关键词匹配
        keyword_match = self._match_keywords(user_input)
        if keyword_match:
            return {
                'method': 'keyword',
                'target': keyword_match['target'],
                'task': user_input,
                'confidence': keyword_match['confidence']
            }

        # 优先级 3: 文件类型检测
        if file_context:
            file_type_match = self._match_file_type(file_context)
            if file_type_match:
                return {
                    'method': 'file_type',
                    'target': file_type_match['target'],
                    'task': user_input,
                    'confidence': file_type_match['confidence']
                }

        # 默认：在主窗口处理
        return {
            'method': 'default',
            'target': None,
            'task': user_input,
            'confidence': 0.0
        }

    def _match_keywords(self, user_input: str) -> Optional[Dict[str, Any]]:
        """关键词匹配"""
        # 兼容两种配置格式
        routes = self.keyword_routes.get('routes', self.keyword_routes.get('keywords', []))

        for route in self._ordered_routes(routes):
            # 获取关键词列表
            keywords = route.get('keywords', route.get('patterns', []))

            for keyword in keywords:
                if keyword.lower() in user_input.lower():
                    target = route.get('target') or route.get('agent') or route.get('agent_alternative')
                    if not self._is_known_target(target):
                        continue
                    return {
                        'target': target,
                        'confidence': route.get('confidence', 0.8)
                    }
        return None

    def _match_file_type(self, file_extension: str) -> Optional[Dict[str, Any]]:
        """文件类型匹配"""
        raw_value = file_extension.strip().casefold()
        basename = Path(raw_value).name
        input_forms = {raw_value, raw_value.lstrip('.'), basename, basename.lstrip('.')}
        suffix = Path(basename).suffix
        if suffix:
            input_forms.update({suffix, suffix.lstrip('.')})

        # 兼容两种配置格式
        routes = self.file_type_routes.get('routes', self.file_type_routes.get('file_types', []))

        for route in self._ordered_routes(routes):
            # 获取扩展名列表
            extensions = route.get('extensions', route.get('patterns', []))

            normalized_extensions = {
                value.casefold() for extension in extensions for value in (extension, extension.lstrip('.'))
            }
            if input_forms & normalized_extensions:
                target = route.get('target') or route.get('agent') or route.get('agent_alternative')
                if not self._is_known_target(target):
                    continue
                return {
                    'target': target,
                    'confidence': route.get('confidence', 0.7)
                }
        return None


# 使用示例
if __name__ == "__main__":
    print("=" * 60)
    print("智能路由引擎 - 显式调用测试")
    print("=" * 60)
    print()

    # 初始化路由引擎
    module_dir = Path(__file__).resolve().parent
    router = IntelligentRouter(
        skills_dir=str(module_dir.parent),
        config_dir=str(module_dir / "config"),
        agents_dir=str(module_dir.parents[2] / "agents"),
    )

    # 测试用例
    test_cases = [
        "[调用技能: pdf] 提取这个 PDF 中的表格数据",
        "[调用 Subagent: backend-dev] 优化这段代码性能",
        "[调用组合: 全栈开发组合] 实现服务并完成测试和审查",
        "帮我审查代码",  # 关键词匹配
        "优化这个组件",  # 需要文件上下文
        "简单的问候",  # 默认处理
    ]

    for i, user_input in enumerate(test_cases, 1):
        print(f"测试 {i}: {user_input}")
        result = router.route(user_input)

        print(f"  路由方式: {result['method']}")
        print(f"  目标: {result['target']}")
        print(f"  任务: {result['task']}")
        print(f"  置信度: {result['confidence']}")
        print()

    print("=" * 60)
