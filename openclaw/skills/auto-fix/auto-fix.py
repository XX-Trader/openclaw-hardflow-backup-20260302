#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Auto-Fix 命令入口

用于通过 /auto-fix 命令快速调用
"""

import sys
import os

# 添加当前目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# 导入并运行主程序
from scripts.main import main

if __name__ == "__main__":
    main()
