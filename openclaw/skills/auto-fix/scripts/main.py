#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Auto-Fix 主控制器

全自动测试-修复循环系统
运行测试 → 分析问题 → 自动修复 → 验证修复 → Git 提交 → 重新测试
循环直到所有测试通过
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime


class Colors:
    """终端颜色"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text):
    """打印标题"""
    print(f"\n{Colors.HEADER}{'=' * 70}{Colors.ENDC}")
    print(f"{Colors.HEADER}  {text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'=' * 70}{Colors.ENDC}\n")


def print_success(text):
    """打印成功信息"""
    print(f"{Colors.OKGREEN}✅ {text}{Colors.ENDC}")


def print_error(text):
    """打印错误信息"""
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")


def print_warning(text):
    """打印警告信息"""
    print(f"{Colors.WARNING}⚠️  {text}{Colors.ENDC}")


def print_info(text):
    """打印信息"""
    print(f"ℹ️  {text}")


def load_config(config_path="auto-fix.config.json"):
    """加载配置文件"""
    config_file = Path(config_path)

    if not config_file.exists():
        print_warning(f"配置文件不存在: {config_path}")
        print_info("将使用默认配置")
        return get_default_config()

    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)

    return config


def get_default_config():
    """获取默认配置"""
    return {
        "version": "1.0",
        "project": {
            "root": "Project",
            "backendPath": "Project/ShengBeiDjango",
            "frontendPath": "Project/ShengBeiVue"
        },
        "test": {
            "configPath": "test.config.json",
            "reportDir": "test_reports"
        },
        "fix": {
            "autoCommit": True,
            "maxIterations": 10,
            "strategy": "balanced"
        },
        "git": {
            "branchPrefix": "auto-fix",
            "autoMerge": True
        },
        "categories": {
            "config": {"enabled": True, "priority": 0, "stage": 0},
            "database": {"enabled": True, "priority": 1, "stage": 1},
            "api": {"enabled": True, "priority": 2, "stage": 1},
            "auth": {"enabled": True, "priority": 3, "stage": 1},
            "frontend": {"enabled": True, "priority": 4, "stage": 2}
        }
    }


def check_documentation(config):
    """检查文档完整性"""
    print_header("文档完整性检查")

    project_root = Path(config["project"]["root"])

    required_docs = [
        project_root / "CLAUDE.md",
        project_root / "INDEX.md",
        Path(config["project"]["backendPath"]) / "INDEX.md",
        Path(config["project"]["frontendPath"]) / "INDEX.md"
    ]

    missing_docs = []
    for doc in required_docs:
        if not doc.exists():
            missing_docs.append(str(doc))

    if missing_docs:
        print_error("文档缺失:")
        for doc in missing_docs:
            print(f"  - {doc}")
        print_warning("\n建议: 先补充缺失的文档")
        return False

    print_success("文档完整性检查: 通过")
    return True


def create_git_branch(config):
    """创建修复分支"""
    branch_name = f"{config['git']['branchPrefix']}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print_info(f"创建修复分支: {branch_name}")

    # 检查 Git 仓库
    result = subprocess.run(
        ["git", "status"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print_error("不是 Git 仓库")
        return None

    # 创建并切换到新分支
    result = subprocess.run(
        ["git", "checkout", "-b", branch_name],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print_error(f"创建分支失败: {result.stderr}")
        return None

    print_success(f"创建修复分支: {branch_name}")
    return branch_name


def run_tests(config):
    """运行测试"""
    print_header("运行测试")

    test_scripts_path = Path(config["test"].get("testScriptsPath", "../deployment-test/scripts"))

    if not test_scripts_path.exists():
        print_error(f"测试脚本路径不存在: {test_scripts_path}")
        return None

    # 运行测试脚本
    test_script = test_scripts_path / "run-all-tests.py"

    if not test_script.exists():
        print_error(f"测试脚本不存在: {test_script}")
        return None

    print_info(f"运行测试: {test_script}")

    result = subprocess.run(
        [sys.executable, str(test_script)],
        capture_output=True,
        text=True,
        cwd=Path.cwd().parent
    )

    print(result.stdout)

    if result.returncode != 0:
        print_warning(f"测试未完全通过 (退出码: {result.returncode})")

    # 返回测试结果（由问题分析器解析）
    return {"success": result.returncode == 0, "exit_code": result.returncode}


def analyze_problems(config, test_results):
    """分析问题"""
    print_header("问题分析")

    # 导入问题分析器
    from .problem_analyzer import ProblemAnalyzer

    analyzer = ProblemAnalyzer(config)

    # 分析测试结果
    problems = analyzer.analyze(test_results)

    if not problems:
        print_success("无问题需要修复")
        return []

    print_info(f"发现 {len(problems)} 个问题:")

    for i, problem in enumerate(problems, 1):
        print(f"  {i}. [{problem.category}] {problem.title}")
        print(f"     严重级别: {problem.severity}")

    return problems


def fix_problems(problems, config, branch_name):
    """修复问题 - 返回 (success, has_complex_problems)"""
    if not problems:
        return True, False

    print_header("开始修复")

    # 导入修复执行器和Git管理器
    from .fix_executor import FixExecutor
    from .git_manager import GitManager

    git_manager = GitManager(config)
    fix_executor = FixExecutor(config, git_manager)

    # 三阶段修复策略
    stages = [
        ("阶段 0: 配置修复", "config"),
        ("阶段 1: 后端依赖链修复", ["database", "api", "auth"]),
        ("阶段 2: 前端修复", "frontend")
    ]

    total_fixed = 0
    total_failed = 0
    total_needs_planning = 0

    for stage_name, categories in stages:
        print_header(stage_name)

        # 筛选当前阶段的问题
        if isinstance(categories, str):
            categories = [categories]

        stage_problems = [p for p in problems if p.category in categories]

        if not stage_problems:
            print_info(f"无 {stage_name} 问题")
            continue

        print_info(f"待修复问题: {len(stage_problems)}")

        # 修复当前阶段的问题
        for problem in stage_problems:
            result = fix_executor.fix(problem)

            if result["success"]:
                total_fixed += 1
                print_success(f"✓ {problem.title}")
            else:
                if result.get("needs_planning"):
                    total_needs_planning += 1
                    print_warning(f"⚠ {problem.title}: {result['message']}")
                else:
                    total_failed += 1
                    print_error(f"✗ {problem.title}: {result['message']}")

    # 打印修复统计
    print_header("修复统计")
    print_info(f"总问题数: {len(problems)}")
    print_success(f"已修复: {total_fixed}")
    print_warning(f"需要规划: {total_needs_planning}")
    print_error(f"修复失败: {total_failed}")

    # 如果有需要规划的问题，停止并提示
    if total_needs_planning > 0:
        print_warning("\n⚠️  发现复杂问题，需要提前规划")
        print_info("请检查上述问题，设计解决方案后再运行")

        # 回滚所有提交
        if config["fix"].get("rollbackOnComplexProblem", True):
            print_info("正在回滚所有修复...")
            git_manager.rollback_last_commit()
            print_warning("已回滚所有修复")

        return False, True  # 修复失败，且有复杂问题

    # 如果全部修复成功，返回True
    if total_fixed == len(problems):
        print_success("\n✅ 所有问题已修复")
        return True, False

    # 如果有部分失败
    if total_failed > 0:
        print_warning(f"\n⚠️  {total_failed} 个问题修复失败")
        return False, False

    return True, False


def merge_to_main(branch_name, config):
    """合并到主分支"""
    print_header("合并到主分支")

    if not config["git"].get("autoMerge", False):
        print_info("自动合并已禁用")
        print_info(f"修复分支保留: {branch_name}")
        return False

    # 切换到主分支
    result = subprocess.run(
        ["git", "checkout", "main"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print_error("切换到主分支失败")
        return False

    # 合并修复分支
    result = subprocess.run(
        ["git", "merge", branch_name],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print_error(f"合并失败: {result.stderr}")
        return False

    print_success(f"已合并到主分支")

    # 删除修复分支
    if config["git"].get("deleteBranchAfterMerge", True):
        result = subprocess.run(
            ["git", "branch", "-d", branch_name],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print_success(f"已删除修复分支: {branch_name}")

    return True


def print_status(status, code, description=""):
    """打印 ralph-wiggum 可解析的状态消息"""
    print(f"\n{Colors.BOLD}{'=' * 70}{Colors.ENDC}")
    print(f"{Colors.BOLD}状态: {status} ({code}){Colors.ENDC}")
    if description:
        print(f"{Colors.OKCYAN}{description}{Colors.ENDC}")
    print(f"{Colors.BOLD}{'=' * 70}{Colors.ENDC}\n")


def main():
    """主函数 - 单次执行模式（配合 ralph-wiggum 循环技能）"""
    print_header("Auto-Fix - 全自动测试-修复循环系统")

    # 解析命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == "--init-config":
        # 初始化配置文件
        config_template = Path(__file__).parent.parent / "templates" / "auto-fix.config.json"
        config_target = Path("auto-fix.config.json")

        import shutil
        shutil.copy(config_template, config_target)
        print_success(f"已生成配置文件: {config_target}")
        print_info("请根据实际情况修改配置后重新运行")
        sys.exit(0)

    # 加载配置
    config = load_config()

    # 检查文档
    if not check_documentation(config):
        print_warning("建议先补充缺失的文档后再运行 Auto-Fix")

        response = input("是否继续？ (y/n): ")
        if response.lower() != 'y':
            print_status("需要人工介入", 1, "文档缺失，请补充文档后继续")
            sys.exit(1)

    # 创建修复分支
    branch_name = create_git_branch(config)
    if not branch_name:
        print_status("需要人工介入", 1, "无法创建修复分支，请检查 Git 状态")
        sys.exit(1)

    # 单次执行：测试 → 分析 → 修复
    print_header("执行修复流程")

    # 运行测试
    test_results = run_tests(config)

    if not test_results:
        print_status("需要人工介入", 1, "测试运行失败，请检查测试环境")
        sys.exit(1)

    # 如果测试通过，直接完成
    if test_results["success"]:
        print_success("🎉 所有测试通过！")

        # 合并到主分支
        merge_success = merge_to_main(branch_name, config)

        if merge_success:
            print_header("Auto-Fix 完成")
            print_success("所有测试通过，已合并到主分支")
            print_status("完成", 0, "所有测试通过，修复流程已完成")
            sys.exit(0)
        else:
            print_warning("合并未完成，修复分支已保留")
            print_info(f"修复分支: {branch_name}")
            print_status("需要人工介入", 1, "合并失败，请手动合并或检查冲突")
            sys.exit(1)

    # 分析问题
    problems = analyze_problems(config, test_results)

    if not problems:
        print_success("✅ 无问题需要修复")

        # 合并到主分支
        merge_success = merge_to_main(branch_name, config)

        if merge_success:
            print_header("Auto-Fix 完成")
            print_success("所有测试通过，已合并到主分支")
            print_status("完成", 0, "所有测试通过，修复流程已完成")
            sys.exit(0)
        else:
            print_warning("合并未完成，修复分支已保留")
            print_info(f"修复分支: {branch_name}")
            print_status("需要人工介入", 1, "合并失败，请手动合并或检查冲突")
            sys.exit(1)

    # 检查问题类型，分离复杂问题和可修复问题
    complex_problems = [p for p in problems if p.severity == "complex"]
    fixable_problems = [p for p in problems if p.severity in ["simple", "medium"]]

    # 如果有复杂问题，提示但继续修复可修复的问题
    if complex_problems:
        print_header("发现复杂问题")
        print_warning(f"发现 {len(complex_problems)} 个复杂问题（需要提前规划）:")
        for problem in complex_problems:
            print(f"  - [{problem.category}] {problem.title}")
        print_info("\n💡 复杂问题将在可修复问题处理完后提示人工规划")

    # 如果全部都是复杂问题，无法自动修复
    if complex_problems and not fixable_problems:
        print_warning("\n所有问题都是复杂问题，无法自动修复")
        print_info("请人工设计和规划解决方案")
        print_status("遇到复杂问题，需要人工规划", 2, f"发现 {len(complex_problems)} 个复杂问题，请人工规划后继续")
        sys.exit(2)

    # 修复可修复的问题（simple 和 medium）
    print_info(f"\n开始修复 {len(fixable_problems)} 个可修复问题...")

    # 传递可修复的问题，而不是所有问题
    success, has_complex = fix_problems(fixable_problems, config, branch_name)

    if not success:
        print_warning("修复未完成，修复分支已保留")
        print_info(f"修复分支: {branch_name}")
        print_info("\n💡 提示: 部分问题已修复，请检查修复历史")
        print_status("需要继续验证", 100, "部分问题已修复，需要重新测试验证")
        sys.exit(100)

    # 如果修复成功但还有复杂问题
    if complex_problems:
        print_header("可修复问题已全部完成")
        print_success(f"✅ 已修复 {len(fixable_problems)} 个可修复问题")
        print_warning(f"⚠️  还有 {len(complex_problems)} 个复杂问题需要人工规划")
        print_info("\n复杂问题列表:")
        for problem in complex_problems:
            print(f"  - [{problem.category}] {problem.title}")
            print(f"    {problem.description[:100]}...")

        # 尝试合并已修复的代码
        merge_success = merge_to_main(branch_name, config)

        if merge_success:
            print_status("遇到复杂问题，需要人工规划", 2, f"可修复问题已合并，但还有 {len(complex_problems)} 个复杂问题需要人工规划")
        else:
            print_status("遇到复杂问题，需要人工规划", 2, f"可修复问题已完成但未合并，还有 {len(complex_problems)} 个复杂问题需要人工规划")

        sys.exit(2)

    # 修复成功，尝试合并
    merge_success = merge_to_main(branch_name, config)

    if not merge_success:
        print_warning("合并未完成，修复分支已保留")
        print_info(f"修复分支: {branch_name}")
        print_status("需要继续验证", 100, "修复完成但合并失败，请重新测试验证")
        sys.exit(100)

    print_header("Auto-Fix 完成")
    print_success("所有问题已修复，已合并到主分支")
    print_status("需要继续验证", 100, "本轮修复完成，建议重新测试验证所有功能")
    sys.exit(100)


if __name__ == "__main__":
    main()
