"""
智能路由引擎
Intelligent Router Engine

负责协调关键词匹配、文件类型检测和 Agent 分发
"""

import json
import os
from typing import Dict, List, Optional, Tuple
from .matcher import KeywordMatcher, FileTypeMatcher
from .dispatcher import AgentDispatcher


class IntelligentRouter:
    """智能路由器主类"""

    def __init__(self, config_dir: str = None):
        """
        初始化路由器

        Args:
            config_dir: 配置文件目录，默认为技能目录下的 config/
        """
        if config_dir is None:
            # 默认配置目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_dir = os.path.join(os.path.dirname(current_dir), "config")

        self.config_dir = config_dir
        self.keyword_matcher = KeywordMatcher(
            os.path.join(config_dir, "keyword_routes.json")
        )
        self.file_matcher = FileTypeMatcher(
            os.path.join(config_dir, "file_type_routes.json")
        )
        self.dispatcher = AgentDispatcher(
            os.path.join(config_dir, "agent_registry.json")
        )

        # 加载配置
        self._load_configs()

    def _load_configs(self):
        """加载所有配置文件"""
        self.keyword_matcher.load_config()
        self.file_matcher.load_config()
        self.dispatcher.load_registry()

    def route(
        self,
        user_input: str,
        file_context: Optional[str] = None,
        explicit_agent: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        根据用户输入和上下文路由到合适的 Agent

        Args:
            user_input: 用户输入文本
            file_context: 当前文件路径或扩展名（可选）
            explicit_agent: 用户显式指定的 Agent（可选）

        Returns:
            路由结果字典，包含：
            - agent: Agent 名称
            - description: Agent 描述
            - reason: 路由原因
            - priority: 优先级
            如果没有匹配则返回 None
        """
        # 1. 优先级最高：用户显式指定
        if explicit_agent:
            result = self.dispatcher.validate_agent(explicit_agent)
            if result:
                result["reason"] = "用户显式指定"
                return result
            else:
                # Agent 不存在，回退到自动匹配
                pass

        # 2. 关键词匹配
        keyword_result = self.keyword_matcher.match(user_input)
        if keyword_result:
            # 验证 Agent 是否存在
            agent_info = self.dispatcher.validate_agent(keyword_result["agent"])
            if agent_info:
                agent_info["reason"] = keyword_result["description"]
                return agent_info

        # 3. 文件类型检测
        if file_context:
            file_result = self.file_matcher.match(file_context)
            if file_result:
                # 验证 Agent 是否存在
                agent_info = self.dispatcher.validate_agent(file_result["agent"])
                if agent_info:
                    agent_info["reason"] = file_result["description"]
                    return agent_info

        # 4. 没有匹配，返回 None（主窗口直接处理）
        return None

    def route_batch(
        self, tasks: List[Dict]
    ) -> List[Optional[Dict]]:
        """
        批量路由多个任务

        Args:
            tasks: 任务列表，每个任务包含 user_input, file_context 等字段

        Returns:
            路由结果列表
        """
        results = []
        for task in tasks:
            result = self.route(
                user_input=task.get("user_input", ""),
                file_context=task.get("file_context"),
                explicit_agent=task.get("explicit_agent"),
            )
            results.append(result)
        return results

    def get_available_agents(self, category: str = None) -> List[Dict]:
        """
        获取可用的 Agent 列表

        Args:
            category: Agent 类别（可选），如果指定则只返回该类别的 Agent

        Returns:
            Agent 信息列表
        """
        return self.dispatcher.get_available_agents(category)

    def get_agent_info(self, agent_name: str) -> Optional[Dict]:
        """
        获取指定 Agent 的详细信息

        Args:
            agent_name: Agent 名称

        Returns:
            Agent 信息字典，如果不存在则返回 None
        """
        return self.dispatcher.get_agent_info(agent_name)

    def reload_configs(self):
        """重新加载配置文件"""
        self._load_configs()


# 使用示例
if __name__ == "__main__":
    # 创建路由器
    router = IntelligentRouter()

    # 示例 1: 关键词匹配
    result1 = router.route("帮我审查这段代码")
    print(f"路由结果 1: {result1}")

    # 示例 2: 文件类型匹配
    result2 = router.route("优化这个组件", file_context="app.vue")
    print(f"路由结果 2: {result2}")

    # 示例 3: 显式指定
    result3 = router.route("优化代码", explicit_agent="python-expert")
    print(f"路由结果 3: {result3}")

    # 示例 4: 批量路由
    tasks = [
        {"user_input": "新增功能"},
        {"user_input": "修复 bug"},
        {"user_input": "部署项目", "file_context": "app.py"},
    ]
    results = router.route_batch(tasks)
    print(f"批量路由结果: {results}")
