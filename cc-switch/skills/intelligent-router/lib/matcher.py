"""
模式匹配器
Pattern Matcher

提供关键词匹配和文件类型检测功能
"""

import json
import os
from typing import Dict, List, Optional


class KeywordMatcher:
    """关键词匹配器"""

    def __init__(self, config_path: str):
        """
        初始化关键词匹配器

        Args:
            config_path: 关键词路由配置文件路径
        """
        self.config_path = config_path
        self.keywords = []

    def load_config(self):
        """加载关键词配置"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self.keywords = config.get("keywords", [])
        except FileNotFoundError:
            print(f"警告: 配置文件不存在 {self.config_path}")
            self.keywords = []
        except json.JSONDecodeError as e:
            print(f"错误: 配置文件格式错误 {e}")
            self.keywords = []

    def match(self, text: str) -> Optional[Dict]:
        """
        匹配文本中的关键词

        Args:
            text: 待匹配的文本

        Returns:
            匹配结果字典，包含：
            - agent: 目标 Agent
            - description: 路由说明
            - priority: 优先级
            - category: 类别
            如果没有匹配则返回 None
        """
        if not text:
            return None

        text_lower = text.lower()

        # 按优先级排序的关键词列表
        sorted_keywords = sorted(self.keywords, key=lambda x: x.get("priority", 10))

        for keyword_group in sorted_keywords:
            patterns = keyword_group.get("patterns", [])
            for pattern in patterns:
                if pattern.lower() in text_lower:
                    return {
                        "agent": keyword_group["agent"],
                        "description": keyword_group["description"],
                        "priority": keyword_group.get("priority", 10),
                        "category": keyword_group.get("category", "未分类"),
                    }

        return None

    def add_keyword(self, patterns: List[str], agent: str, description: str,
                    priority: int = 10, category: str = "自定义"):
        """
        添加关键词规则（仅运行时有效）

        Args:
            patterns: 关键词列表
            agent: 目标 Agent
            description: 路由说明
            priority: 优先级
            category: 类别
        """
        self.keywords.append({
            "patterns": patterns,
            "agent": agent,
            "description": description,
            "priority": priority,
            "category": category,
        })

    def get_all_keywords(self) -> List[Dict]:
        """获取所有关键词规则"""
        return self.keywords


class FileTypeMatcher:
    """文件类型匹配器"""

    def __init__(self, config_path: str):
        """
        初始化文件类型匹配器

        Args:
            config_path: 文件类型路由配置文件路径
        """
        self.config_path = config_path
        self.file_types = []

    def load_config(self):
        """加载文件类型配置"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                self.file_types = config.get("file_types", [])
        except FileNotFoundError:
            print(f"警告: 配置文件不存在 {self.config_path}")
            self.file_types = []
        except json.JSONDecodeError as e:
            print(f"错误: 配置文件格式错误 {e}")
            self.file_types = []

    def match(self, file_path_or_ext: str) -> Optional[Dict]:
        """
        匹配文件路径或扩展名

        Args:
            file_path_or_ext: 文件路径或扩展名（如 ".py" 或 "app.py"）

        Returns:
            匹配结果字典，包含：
            - agent: 目标 Agent
            - description: 路由说明
            - priority: 优先级
            - category: 类别
            如果没有匹配则返回 None
        """
        if not file_path_or_ext:
            return None

        # 提取文件扩展名
        if "." in file_path_or_ext:
            # 如果是完整路径，提取扩展名
            ext = os.path.splitext(file_path_or_ext)[1].lower()
        else:
            # 如果已经是扩展名，直接使用
            ext = file_path_or_ext.lower()

        # 按优先级排序的文件类型列表
        sorted_file_types = sorted(
            self.file_types, key=lambda x: x.get("priority", 10)
        )

        for file_type in sorted_file_types:
            extensions = file_type.get("extensions", [])
            if ext in extensions:
                return {
                    "agent": file_type["agent"],
                    "description": file_type["description"],
                    "priority": file_type.get("priority", 10),
                    "category": file_type.get("category", "未分类"),
                }

        return None

    def add_file_type(self, extensions: List[str], agent: str, description: str,
                     priority: int = 10, category: str = "自定义"):
        """
        添加文件类型规则（仅运行时有效）

        Args:
            extensions: 文件扩展名列表（如 [".py", ".pyw"]）
            agent: 目标 Agent
            description: 路由说明
            priority: 优先级
            category: 类别
        """
        self.file_types.append({
            "extensions": extensions,
            "agent": agent,
            "description": description,
            "priority": priority,
            "category": category,
        })

    def get_all_file_types(self) -> List[Dict]:
        """获取所有文件类型规则"""
        return self.file_types


# 使用示例
if __name__ == "__main__":
    # 关键词匹配器示例
    keyword_matcher = KeywordMatcher(
        "../config/keyword_routes.json"
    )
    keyword_matcher.load_config()

    result = keyword_matcher.match("帮我审查这段代码")
    print(f"关键词匹配结果: {result}")

    # 文件类型匹配器示例
    file_matcher = FileTypeMatcher(
        "../config/file_type_routes.json"
    )
    file_matcher.load_config()

    result = file_matcher.match("app.vue")
    print(f"文件类型匹配结果: {result}")
