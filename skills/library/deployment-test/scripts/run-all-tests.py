#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
部署后测试 - 一键运行所有测试
用法: python run-all-tests.py
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path

# 添加脚本目录到 Python 路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# 导入测试模块
import test_ports
import test_api
import test_ui


def load_config(config_path="test.config.json"):
    """加载测试配置"""
    if not os.path.exists(config_path):
        print(f"❌ 配置文件不存在: {config_path}")
        print(f"请从 templates/test.config.json 复制并修改配置")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 替换占位符
    if 'testAccounts' in config:
        email = config['testAccounts'].get('email', '')
        password = config['testAccounts'].get('password', '')

        # 替换 API 测试中的占位符
        if 'apiEndpoints' in config:
            for endpoint in config['apiEndpoints']:
                if 'body' in endpoint:
                    if isinstance(endpoint['body'], str):
                        endpoint['body'] = endpoint['body'].replace('{{email}}', email)
                        endpoint['body'] = endpoint['body'].replace('{{password}}', password)
                    elif isinstance(endpoint['body'], dict):
                        for key, value in endpoint['body'].items():
                            if isinstance(value, str):
                                endpoint['body'][key] = value.replace('{{email}}', email).replace('{{password}}', password)

        # 替换 UI 测试中的占位符
        if 'uiTests' in config:
            for test in config['uiTests']:
                if 'actions' in test:
                    for action in test['actions']:
                        if 'value' in action and isinstance(action['value'], str):
                            action['value'] = action['value'].replace('{{email}}', email).replace('{{password}}', password)

    return config


def generate_report(config, port_results, api_results, ui_results):
    """生成测试报告"""
    report_dir = Path(config.get('report', {}).get('outputDir', 'test_reports'))
    report_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    report_path = report_dir / f'deployment-test-report-{timestamp}.md'

    # 读取报告模板
    template_path = SCRIPT_DIR.parent / 'templates' / 'test-report.md'
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()

    # 计算统计
    total_tests = 0
    passed_tests = 0
    failed_tests = 0

    # 端口测试统计
    if port_results:
        for result in port_results.get('results', []):
            total_tests += 1
            if result.get('status') == '✅ 正常':
                passed_tests += 1
            else:
                failed_tests += 1

    # API 测试统计
    if api_results:
        for result in api_results.get('results', []):
            total_tests += 1
            if result.get('result') == '✅':
                passed_tests += 1
            else:
                failed_tests += 1

    # UI 测试统计
    if ui_results:
        for result in ui_results.get('results', []):
            total_tests += 1
            if result.get('result') == '✅':
                passed_tests += 1
            else:
                failed_tests += 1

    pass_rate = f"{(passed_tests / total_tests * 100):.1f}%" if total_tests > 0 else "0%"

    # 填充模板
    content = template.replace('{{projectName}}', config.get('projectName', ''))
    content = content.replace('{{testTime}}', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    content = content.replace('{{tester}}', config.get('tester', ''))
    content = content.replace('{{environment}}', '本地开发环境')
    content = content.replace('{{totalTests}}', str(total_tests))
    content = content.replace('{{passedTests}}', str(passed_tests))
    content = content.replace('{{failedTests}}', str(failed_tests))
    content = content.replace('{{passRate}}', pass_rate)

    # 端口测试结果表格
    port_table = ""
    for result in port_results.get('results', []):
        port_table += f"| {result.get('service', '')} | {result.get('port', '')} | {result.get('status', '')} | {result.get('response_time', '')} | {result.get('remark', '')} |\n"
    content = content.replace('{{portTestResults}}', port_table)

    # API 测试结果表格
    api_table = ""
    for result in api_results.get('results', []):
        api_table += f"| {result.get('name', '')} | {result.get('method', '')} | {result.get('path', '')} | {result.get('expectedStatus', '')} | {result.get('actualStatus', '')} | {result.get('expectedCode', '')} | {result.get('actualCode', '')} | {result.get('result', '')} |\n"
    content = content.replace('{{apiTestResults}}', api_table)

    # UI 测试结果表格
    ui_table = ""
    for result in ui_results.get('results', []):
        screenshot = f"[查看]({result.get('screenshot', '')})" if result.get('screenshot') else ""
        ui_table += f"| {result.get('name', '')} | {result.get('url', '')} | {result.get('action', '')} | {result.get('result', '')} | {screenshot} |\n"
    content = content.replace('{{uiTestResults}}', ui_table)

    # 失败详情
    failures = ""

    if port_results.get('failures'):
        failures += "### 端口检测失败\n\n"
        for failure in port_results.get('failures', []):
            failures += f"- **{failure.get('service', '')}**: {failure.get('reason', '')}\n\n"

    if api_results.get('failures'):
        failures += "### API 测试失败\n\n"
        for failure in api_results.get('failures', []):
            failures += f"- **{failure.get('name', '')}**: {failure.get('reason', '')}\n"
            if failure.get('details'):
                failures += f"  错误信息: `{failure.get('details')}`\n\n"

    if ui_results.get('failures'):
        failures += "### UI 测试失败\n\n"
        for failure in ui_results.get('failures', []):
            failures += f"- **{failure.get('name', '')}**: {failure.get('reason', '')}\n\n"

    content = content.replace('{{portTestDetails}}', port_results.get('details', ''))
    content = content.replace('{{apiTestFailures}}', api_results.get('failures_text', ''))
    content = content.replace('{{uiTestFailures}}', ui_results.get('failures_text', ''))
    content = content.replace('{{criticalIssues}}', failures if failures else "无")
    content = content.replace('{{majorIssues}}', "无")
    content = content.replace('{{minorIssues}}', "无")
    content = content.replace('{{immediateFixes}}', "无")
    content = content.replace('{{futureImprovements}}', "无")
    content = content.replace('{{apiTestSuccess}}', api_results.get('success_text', ''))
    content = content.replace('{{uiTestSuccess}}', ui_results.get('success_text', ''))
    content = content.replace('{{testConfig}}', json.dumps(config, indent=2, ensure_ascii=False))
    content = content.replace('{{testLogs}}', "")
    content = content.replace('{{reportTime}}', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # 写入报告
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return report_path


def main():
    print("=" * 60)
    print("  部署后自动化测试")
    print("=" * 60)
    print()

    # 查找配置文件
    config_paths = ['test.config.json', '../test.config.json']
    config_path = None
    for path in config_paths:
        if os.path.exists(path):
            config_path = path
            break

    if not config_path:
        print("❌ 未找到配置文件 test.config.json")
        print("请从 templates/test.config.json 复制并修改配置")
        sys.exit(1)

    # 加载配置
    print(f"📋 加载配置: {config_path}")
    config = load_config(config_path)
    print(f"   项目名称: {config.get('projectName', '')}")
    print(f"   测试人员: {config.get('tester', '')}")
    print()

    # 运行测试
    all_results = {}

    # 1. 端口检测
    print("🔍 [1/3] 端口检测...")
    port_results = test_ports.run_tests(config)
    all_results['port'] = port_results
    print(f"   完成: {len(port_results.get('results', []))} 个服务检测")
    print()

    # 2. API 测试
    print("🌐 [2/3] API 测试...")
    api_results = test_api.run_tests(config)
    all_results['api'] = api_results
    print(f"   完成: {len(api_results.get('results', []))} 个接口测试")
    print()

    # 3. UI 测试
    if config.get('services', {}).get('frontend', {}).get('enabled', True):
        print("🎨 [3/3] UI 测试...")
        ui_results = test_ui.run_tests(config)
        all_results['ui'] = ui_results
        print(f"   完成: {len(ui_results.get('results', []))} 个 UI 测试")
        print()
    else:
        print("🎨 [3/3] UI 测试... (跳过)")
        ui_results = {'results': [], 'failures': []}
        all_results['ui'] = ui_results
        print()

    # 生成报告
    print("📝 生成测试报告...")
    report_path = generate_report(
        config,
        port_results,
        api_results,
        ui_results
    )
    print(f"   报告已生成: {report_path}")
    print()

    # 显示汇总
    print("=" * 60)
    print("  测试完成")
    print("=" * 60)
    print()

    # 计算统计
    total_tests = 0
    passed_tests = 0

    for module in ['port', 'api', 'ui']:
        for result in all_results[module].get('results', []):
            total_tests += 1
            if '✅' in str(result.get('result', result.get('status', ''))):
                passed_tests += 1

    failed_tests = total_tests - passed_tests
    pass_rate = f"{(passed_tests / total_tests * 100):.1f}%" if total_tests > 0 else "0%"

    print(f"总测试项: {total_tests}")
    print(f"通过: {passed_tests}")
    print(f"失败: {failed_tests}")
    print(f"通过率: {pass_rate}")
    print()

    if failed_tests > 0:
        print("⚠️  存在测试失败，请查看报告详情")
        sys.exit(1)
    else:
        print("✅ 所有测试通过！")
        sys.exit(0)


if __name__ == '__main__':
    main()
