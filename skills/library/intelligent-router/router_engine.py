#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能路由引擎 - 支持显式调用
"""
import re
import json
import os
from typing import Optional, Dict, Any

class ExplicitCallDetector:
    """显式调用检测器"""

    def __init__(self, config_path: str):
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
        # TODO: 实现实际的验证逻辑
        # 1. 检查技能目录是否存在
        # 2. 检查 Subagent 是否在列表中
        # 3. 检查组合是否定义

        return True  # 简化示例


class IntelligentRouter:
    """智能路由引擎"""

    def __init__(self, skills_dir: str, config_dir: str):
        """初始化路由引擎

        Args:
            skills_dir: 技能目录
            config_dir: 配置目录
        """
        self.skills_dir = skills_dir
        self.config_dir = config_dir

        # 加载配置
        self.explicit_detector = ExplicitCallDetector(
            os.path.join(config_dir, 'intent_patterns.json')
        )

        with open(os.path.join(config_dir, 'keyword_routes.json'), 'r', encoding='utf-8') as f:
            self.keyword_routes = json.load(f)

        with open(os.path.join(config_dir, 'file_type_routes.json'), 'r', encoding='utf-8') as f:
            self.file_type_routes = json.load(f)

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
        if explicit_call:
            return {
                'method': 'explicit',
                'target': explicit_call['name'],
                'task': explicit_call['task'],
                'type': explicit_call['type'],
                'confidence': 1.0,
                'raw_match': explicit_call['raw_match']
            }

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

        for route in routes:
            # 获取关键词列表
            keywords = route.get('keywords', route.get('patterns', []))

            for keyword in keywords:
                if keyword.lower() in user_input.lower():
                    return {
                        'target': route.get('target', route.get('agent')),
                        'confidence': route.get('confidence', 0.8)
                    }
        return None

    def _match_file_type(self, file_extension: str) -> Optional[Dict[str, Any]]:
        """文件类型匹配"""
        # 移除点号
        ext = file_extension.lstrip('.')

        # 兼容两种配置格式
        routes = self.file_type_routes.get('routes', self.file_type_routes.get('file_types', []))

        for route in routes:
            # 获取扩展名列表
            extensions = route.get('extensions', route.get('patterns', []))

            if ext in extensions:
                return {
                    'target': route.get('target', route.get('agent')),
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
    router = IntelligentRouter(
        skills_dir=os.path.expanduser("~/.claude/skills"),
        config_dir=os.path.expanduser("~/.claude/skills/intelligent-router/config")
    )

    # 测试用例
    test_cases = [
        "[调用技能: pdf] 提取这个 PDF 中的表格数据",
        "[调用 Subagent: smart-flow:python-expert] 优化这段代码性能",
        "[调用组合: 数据分析组合] 分析这个数据管道的质量和性能",
        "帮我审查这段代码",  # 关键词匹配
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
