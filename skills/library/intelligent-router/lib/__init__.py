"""
智能路由插件库
Intelligent Router Plugin Library

提供任务路由、匹配和分发功能
"""

from .router import IntelligentRouter
from .matcher import KeywordMatcher, FileTypeMatcher
from .dispatcher import AgentDispatcher

__version__ = "1.0.0"
__all__ = ["IntelligentRouter", "KeywordMatcher", "FileTypeMatcher", "AgentDispatcher"]
