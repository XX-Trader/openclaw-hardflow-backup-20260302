"""配置管理器"""

import json
import os
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path


@dataclass
class Config:
    """配置数据类"""
    version: str = "1.0.0"
    created_at: str = ""
    last_updated: str = ""
    description: str = "日志去重配置文件"

    # 规则配置
    rules: List[Dict[str, Any]] = field(default_factory=list)

    # 异常配置
    exceptions: Dict[str, Any] = field(default_factory=lambda: {
        "log_levels": ["ERROR", "WARN", "WARNING", "CRITICAL", "FATAL"],
        "keywords": ["exception", "failed", "timeout", "error", "panic"],
        "custom_patterns": []
    })

    # 输出配置
    output: Dict[str, Any] = field(default_factory=lambda: {
        "deduped_suffix": "-deduped",
        "report_name": "report.txt",
        "preview_lines": 5
    })

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.last_updated:
            self.last_updated = datetime.now().isoformat()


class ConfigManager:
    """配置管理器"""

    DEFAULT_CONFIG_DIR = "~/.log-dedup"
    DEFAULT_CONFIG_FILE = "config.json"

    def __init__(self, config_dir: Optional[str] = None):
        """
        初始化配置管理器

        Args:
            config_dir: 配置目录，默认为 ~/.log-dedup
        """
        self.config_dir = Path(config_dir or self.DEFAULT_CONFIG_DIR).expanduser()
        self.config_file = self.config_dir / self.DEFAULT_CONFIG_FILE
        self.config: Optional[Config] = None

    def ensure_config_dir(self):
        """确保配置目录存在"""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> Config:
        """加载配置文件"""
        if not self.config_file.exists():
            # 创建默认配置
            self.config = Config()
            self.save()
            return self.config

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.config = Config(**data)
                return self.config
        except Exception as e:
            print(f"⚠️  加载配置文件失败: {e}")
            print("使用默认配置")
            self.config = Config()
            return self.config

    def save(self):
        """保存配置文件"""
        if not self.config:
            raise ValueError("没有可保存的配置")

        self.config.last_updated = datetime.now().isoformat()
        self.ensure_config_dir()

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(self.config), f, indent=2, ensure_ascii=False)
            print(f"✓ 配置已保存到: {self.config_file}")
        except Exception as e:
            print(f"⚠️  保存配置文件失败: {e}")

    def update_rules(self, rules_data: List[Dict[str, Any]]):
        """更新规则配置"""
        if not self.config:
            self.config = self.load()
        self.config.rules = rules_data
        self.save()

    def get_config_path(self) -> str:
        """获取配置文件路径"""
        return str(self.config_file)
