"""
Agent 分发器
Agent Dispatcher

负责验证 Agent 可用性并分发任务
"""

import json
import os
from typing import Dict, List, Optional


class AgentDispatcher:
    """Agent 分发器"""

    def __init__(self, registry_path: str):
        """
        初始化分发器

        Args:
            registry_path: Agent 注册表文件路径
        """
        self.registry_path = registry_path
        self.agent_registry = {}

    def load_registry(self):
        """加载 Agent 注册表"""
        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                agents_list = config.get("agents", [])
                # 转换为字典，方便快速查找
                self.agent_registry = {
                    agent["name"]: agent
                    for agent in agents_list
                    if agent.get("available", True)
                }
        except FileNotFoundError:
            print(f"警告: Agent 注册表不存在 {self.registry_path}")
            self.agent_registry = {}
        except json.JSONDecodeError as e:
            print(f"错误: Agent 注册表格式错误 {e}")
            self.agent_registry = {}

    def validate_agent(self, agent_name: str) -> Optional[Dict]:
        """
        验证 Agent 是否可用

        Args:
            agent_name: Agent 名称

        Returns:
            Agent 信息字典，如果不可用则返回 None
        """
        agent = self.agent_registry.get(agent_name)
        if agent and agent.get("available", True):
            return {
                "name": agent["name"],
                "description": agent["description"],
                "category": agent.get("category", "未分类"),
                "capabilities": agent.get("capabilities", []),
                "priority": agent.get("priority", 10),
            }
        return None

    def get_available_agents(self, category: str = None) -> List[Dict]:
        """
        获取可用的 Agent 列表

        Args:
            category: Agent 类别（可选），如果指定则只返回该类别的 Agent

        Returns:
            Agent 信息列表
        """
        agents = list(self.agent_registry.values())

        if category:
            agents = [a for a in agents if a.get("category") == category]

        # 按优先级排序
        agents = sorted(agents, key=lambda x: x.get("priority", 10))

        return [
            {
                "name": a["name"],
                "description": a["description"],
                "category": a.get("category", "未分类"),
                "capabilities": a.get("capabilities", []),
                "priority": a.get("priority", 10),
            }
            for a in agents
        ]

    def get_agent_info(self, agent_name: str) -> Optional[Dict]:
        """
        获取指定 Agent 的详细信息

        Args:
            agent_name: Agent 名称

        Returns:
            Agent 信息字典，如果不存在则返回 None
        """
        agent = self.agent_registry.get(agent_name)
        if agent:
            return {
                "name": agent["name"],
                "description": agent["description"],
                "category": agent.get("category", "未分类"),
                "capabilities": agent.get("capabilities", []),
                "priority": agent.get("priority", 10),
                "available": agent.get("available", True),
            }
        return None

    def search_agents(self, keyword: str) -> List[Dict]:
        """
        搜索包含关键词的 Agent

        Args:
            keyword: 搜索关键词（匹配名称、描述或能力）

        Returns:
            匹配的 Agent 列表
        """
        keyword_lower = keyword.lower()
        matched_agents = []

        for agent in self.agent_registry.values():
            # 搜索名称、描述和能力
            if (
                keyword_lower in agent["name"].lower()
                or keyword_lower in agent["description"].lower()
                or any(
                    keyword_lower in str(cap).lower()
                    for cap in agent.get("capabilities", [])
                )
            ):
                matched_agents.append(agent)

        # 按优先级排序
        matched_agents = sorted(
            matched_agents, key=lambda x: x.get("priority", 10)
        )

        return [
            {
                "name": a["name"],
                "description": a["description"],
                "category": a.get("category", "未分类"),
                "capabilities": a.get("capabilities", []),
                "priority": a.get("priority", 10),
            }
            for a in matched_agents
        ]

    def get_categories(self) -> List[str]:
        """
        获取所有 Agent 类别

        Returns:
            类别列表
        """
        categories = set()
        for agent in self.agent_registry.values():
            categories.add(agent.get("category", "未分类"))
        return sorted(list(categories))

    def get_stats(self) -> Dict:
        """
        获取 Agent 统计信息

        Returns:
            统计信息字典，包含：
            - total: 总 Agent 数量
            - available: 可用 Agent 数量
            - categories: 类别列表
            - by_category: 按类别分组的 Agent 数量
        """
        total = len(self.agent_registry)
        categories = self.get_categories()

        by_category = {}
        for category in categories:
            count = len([
                a for a in self.agent_registry.values()
                if a.get("category") == category
            ])
            by_category[category] = count

        return {
            "total": total,
            "available": total,  # registry 中已过滤不可用的
            "categories": categories,
            "by_category": by_category,
        }


# 使用示例
if __name__ == "__main__":
    dispatcher = AgentDispatcher("../config/agent_registry.json")
    dispatcher.load_registry()

    # 示例 1: 验证 Agent
    info = dispatcher.validate_agent("code-reviewer")
    print(f"Agent 信息: {info}")

    # 示例 2: 获取所有可用 Agent
    agents = dispatcher.get_available_agents()
    print(f"所有可用 Agent: {len(agents)} 个")

    # 示例 3: 按类别获取 Agent
    frontend_agents = dispatcher.get_available_agents("Development & Architecture")
    print(f"开发架构 Agent: {len(frontend_agents)} 个")

    # 示例 4: 搜索 Agent
    results = dispatcher.search_agents("python")
    print(f"搜索 'python': {len(results)} 个结果")

    # 示例 5: 统计信息
    stats = dispatcher.get_stats()
    print(f"统计信息: {stats}")
