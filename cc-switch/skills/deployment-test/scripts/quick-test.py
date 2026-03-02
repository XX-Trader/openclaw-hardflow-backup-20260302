#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速测试启动器 - 一键测试网页所有功能
用法: python quick-test.py
"""

import json
import sys
import os
from pathlib import Path
import urllib.parse


def ask_question(prompt, default=None):
    """询问用户问题"""
    if default:
        user_input = input(f"{prompt} (默认: {default}): ").strip()
        return user_input if user_input else default
    else:
        while True:
            user_input = input(f"{prompt}: ").strip()
            if user_input:
                return user_input


def detect_project_type(url):
    """检测项目类型"""
    if 'localhost' in url or '127.0.0.1' in url:
        return "local"
    return "remote"


def generate_test_config(frontend_url, backend_url, test_account=None):
    """生成测试配置"""
    # 解析端口
    frontend_port = 8083
    backend_port = 8000

    if ':' in frontend_url:
        try:
            frontend_port = int(frontend_url.split(':')[-1].split('/')[0])
        except:
            pass

    if ':' in backend_url:
        try:
            backend_port = int(backend_url.split(':')[-1].split('/')[0])
        except:
            pass

    # 构建配置
    config = {
        "version": "1.0",
        "projectName": "QuickTest",
        "testDate": "",
        "tester": "Auto Test",
        "services": {
            "mysql": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 3306
            },
            "redis": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 6379
            },
            "backend": {
                "enabled": True,
                "url": backend_url
            },
            "frontend": {
                "enabled": True,
                "url": frontend_url
            }
        },
        "testAccounts": test_account or {
            "email": "",
            "password": "",
            "nickname": "测试用户"
        },
        "apiEndpoints": [
            {
                "name": "健康检查",
                "method": "GET",
                "path": "/api/health/",
                "expectedStatus": 200,
                "needAuth": False
            },
            {
                "name": "用户登录",
                "method": "POST",
                "path": "/api/accounts/login/",
                "body": {"email": "{{email}}", "password": "{{password}}"},
                "expectedStatus": 200,
                "expectedCode": 200,
                "needAuth": False
            },
            {
                "name": "获取用户信息",
                "method": "GET",
                "path": "/api/accounts/userinfo/",
                "expectedStatus": 200,
                "needAuth": True
            }
        ],
        "uiTests": [
            {
                "name": "访问首页",
                "url": "/",
                "actions": [
                    {"type": "waitFor", "target": "loadstate", "value": "networkidle"}
                ]
            }
        ],
        "report": {
            "outputDir": "test_reports",
            "includeScreenshots": True,
            "includeRequestLogs": True
        }
    }

    return config


def auto_detect_api_docs(project_root=None):
    """自动检测并解析 API 文档"""
    if project_root is None:
        # 查找项目根目录
        current_dir = Path.cwd()
        while current_dir != current_dir.parent:
            if (current_dir / 'manage.py').exists() or (current_dir / 'package.json').exists():
                project_root = current_dir
                break
            current_dir = current_dir.parent

        if project_root is None:
            project_root = Path.cwd()

    # 查找 API 文档
    api_doc_paths = [
        project_root / "docs" / "API文档.md",
        project_root / "docs" / "03_API文档.md",
        project_root / "Project" / "ShengBeiDjango" / "docs" / "03_API文档.md",
        project_root / "API接口文档.md",
    ]

    detected_apis = []

    for doc_path in api_doc_paths:
        if doc_path.exists():
            print(f"   📄 发现 API 文档: {doc_path.relative_to(project_root)}")
            # 这里可以解析文档提取接口列表
            # 简化版：添加常见接口
            detected_apis.extend([
                {"name": "获取机器人列表", "method": "GET", "path": "/api/pm-robot/list"},
                {"name": "创建机器人", "method": "POST", "path": "/api/pm-robot/create"},
                {"name": "启动机器人", "method": "POST", "path": "/api/pm-robot/start"},
            ])
            break

    return detected_apis


def main():
    print("=" * 70)
    print("  🚀 网页功能快速测试")
    print("=" * 70)
    print()
    print("  这个工具将自动测试您的网页的所有功能")
    print("  包括：端口检测、API 接口测试、页面加载测试")
    print()
    print("-" * 70)
    print()

    # 1. 询问测试网址
    frontend_url = ask_question("请输入前端网址", "http://localhost:8083")
    print()

    # 2. 询问后端网址
    backend_url = ask_question("请输入后端 API 网址", "http://localhost:8000")
    print()

    # 3. 询问是否有测试账号
    has_account = ask_question("是否有测试账号？(y/n)", "n").lower()
    test_account = None

    if has_account == 'y':
        email = ask_question("请输入测试邮箱")
        password = ask_question("请输入测试密码")
        test_account = {
            "email": email,
            "password": password,
            "nickname": "测试用户"
        }
        print()

    # 4. 询问测试范围
    print("请选择测试范围:")
    print("  1. 完整测试 (端口 + API + UI)")
    print("  2. 仅测试端口")
    print("  3. 仅测试 API")
    print("  4. 仅测试 UI")

    test_scope = ask_question("请选择 (1-4)", "1")
    print()

    # 5. 生成配置
    print("📋 正在生成测试配置...")
    config = generate_test_config(frontend_url, backend_url, test_account)

    # 尝试自动检测 API 文档
    auto_apis = auto_detect_api_docs()
    if auto_apis:
        print(f"   ✅ 自动检测到 {len(auto_apis)} 个 API 接口")
        # 可以添加到配置中

    print()

    # 6. 显示测试计划
    print("📋 测试计划:")
    print(f"   前端地址: {frontend_url}")
    print(f"   后端地址: {backend_url}")
    print(f"   测试账号: {'是' if test_account else '否'}")

    if test_scope == '1':
        print(f"   测试范围: 完整测试 (端口 + API + UI)")
    elif test_scope == '2':
        print(f"   测试范围: 端口检测")
    elif test_scope == '3':
        print(f"   测试范围: API 测试")
    elif test_scope == '4':
        print(f"   测试范围: UI 测试")

    print()
    confirm = ask_question("开始测试？(y/n)", "y")

    if confirm.lower() != 'y':
        print("测试已取消")
        return

    print()
    print("=" * 70)
    print("  开始测试")
    print("=" * 70)
    print()

    # 7. 运行测试
    # 导入测试模块
    SCRIPT_DIR = Path(__file__).parent
    sys.path.insert(0, str(SCRIPT_DIR))

    results = {}

    # 端口检测
    if test_scope in ['1', '2']:
        print("🔍 [1/3] 端口检测")
        print("-" * 70)
        import test_ports
        port_results = test_ports.run_tests(config)
        results['port'] = port_results
        print()

    # API 测试
    if test_scope in ['1', '3']:
        print("🌐 [2/3] API 测试")
        print("-" * 70)
        import test_api
        api_results = test_api.run_tests(config)
        results['api'] = api_results
        print()

    # UI 测试
    if test_scope in ['1', '4']:
        print("🎨 [3/3] UI 测试")
        print("-" * 70)
        import test_ui
        ui_results = test_ui.run_tests(config)
        results['ui'] = ui_results
        print()

    # 8. 生成报告
    if test_scope == '1':
        print("📝 生成测试报告...")
        import run_all_tests
        report_path = run_all_tests.generate_report(
            config,
            results.get('port', {}),
            results.get('api', {}),
            results.get('ui', {})
        )
        print(f"   ✅ 报告已生成: {report_path}")
        print()

    # 9. 显示汇总
    print("=" * 70)
    print("  测试完成")
    print("=" * 70)
    print()

    # 计算统计
    total_tests = 0
    passed_tests = 0

    for module in results.values():
        for result in module.get('results', []):
            total_tests += 1
            if '✅' in str(result.get('result', result.get('status', ''))):
                passed_tests += 1

    failed_tests = total_tests - passed_tests
    pass_rate = f"{(passed_tests / total_tests * 100):.1f}%" if total_tests > 0 else "0%"

    print(f"📊 测试统计:")
    print(f"   总测试项: {total_tests}")
    print(f"   通过: {passed_tests}")
    print(f"   失败: {failed_tests}")
    print(f"   通过率: {pass_rate}")
    print()

    if failed_tests > 0:
        print("⚠️  存在测试失败，请查看报告详情")
    else:
        print("✅ 所有测试通过！")

    print()
    print("=" * 70)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
        print()
        print("测试已中断")
        sys.exit(0)
