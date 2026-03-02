#!/usr/bin/env python3
"""
仓库合并技能 - 交互式初始化脚本
一键启动上游合并流程

使用方法：
    python init_repo_sync.py

或在 Claude Code 中说：
    "启动仓库合并流程"

作者: Claude Code Agent
版本: v1.0
日期: 2026-01-07
"""

import os
import sys
import subprocess
import json
from datetime import datetime
from pathlib import Path


class RepoSyncInitializer:
    """仓库合并初始化器"""

    def __init__(self):
        self.config = {}
        self.config_file = '.repo-sync-config.json'

    def print_banner(self):
        """打印横幅"""
        print("=" * 80)
        print("🔄 仓库合并技能 - 上游同步工具")
        print("=" * 80)
        print()
        print("本工具将帮助您安全地合并上游仓库更新，同时保留您的自定义修改。")
        print()

    def check_git_repo(self):
        """检查是否在Git仓库中"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                capture_output=True,
                text=True,
                check=True
            )
            print("✅ 检测到Git仓库")
            return True
        except subprocess.CalledProcessError:
            print("❌ 错误：当前目录不是Git仓库")
            print("   请在Git仓库根目录中运行此脚本")
            return False

    def get_current_branch(self):
        """获取当前分支"""
        result = subprocess.run(
            ['git', 'branch', '--show-current'],
            capture_output=True,
            text=True,
            check=True
        )
        branch = result.stdout.strip()
        print(f"✅ 当前分支: {branch}")
        return branch

    def check_working_tree_clean(self):
        """检查工作区是否干净"""
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True,
            text=True,
            check=True
        )

        if result.stdout.strip():
            print("⚠️  工作区有未提交的更改：")
            print(result.stdout)
            response = input("是否继续？(yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                return False
        else:
            print("✅ 工作区干净")

        return True

    def list_remotes(self):
        """列出所有远程仓库"""
        result = subprocess.run(
            ['git', 'remote', '-v'],
            capture_output=True,
            text=True,
            check=True
        )

        remotes = {}
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                name = parts[0]
                url = parts[1]
                remotes[name] = url

        print("\n📋 已配置的远程仓库：")
        for name, url in remotes.items():
            print(f"   - {name}: {url}")

        return remotes

    def detect_upstream(self, remotes):
        """自动检测upstream仓库"""
        # 常见的upstream名称
        upstream_names = ['upstream', 'fmz-source', 'original', 'source']

        for name in upstream_names:
            if name in remotes:
                print(f"\n✅ 自动检测到上游仓库: {name}")
                return name

        return None

    def ask_upstream(self, remotes):
        """询问上游仓库信息"""
        upstream = self.detect_upstream(remotes)

        if upstream:
            use_detected = input(f"是否使用 {upstream} 作为上游？(yes/no): ").strip().lower()
            if use_detected in ['yes', 'y']:
                return upstream

        print("\n⚠️  未检测到上游仓库，请手动配置：")
        print("   选项1: 输入已存在的远程仓库名称")
        print("   选项2: 输入上游仓库URL（将自动添加为upstream）")

        choice = input("\n请选择 (1/2): ").strip()

        if choice == '1':
            # 使用现有远程仓库
            print("\n可用的远程仓库：")
            for name in remotes.keys():
                print(f"   - {name}")

            upstream = input("\n请输入上游仓库名称: ").strip()
            if upstream not in remotes:
                print(f"❌ 错误：远程仓库 '{upstream}' 不存在")
                return None

        elif choice == '2':
            # 添加新的远程仓库
            upstream_url = input("请输入上游仓库URL: ").strip()
            upstream = 'upstream'

            print(f"\n📌 添加上游仓库: {upstream} -> {upstream_url}")
            subprocess.run(
                ['git', 'remote', 'add', upstream, upstream_url],
                check=True
            )
            print(f"✅ 已添加上游仓库: {upstream}")

        else:
            print("❌ 无效选择")
            return None

        return upstream

    def detect_fork_point(self, upstream):
        """检测fork起点（第一次与上游分叉的commit）"""
        try:
            # 查找与上游分叉的点
            result = subprocess.run(
                ['git', 'merge-base', 'HEAD', f'{upstream}/main'],
                capture_output=True,
                text=True,
                check=True
            )

            fork_point = result.stdout.strip()

            # 获取commit信息
            result2 = subprocess.run(
                ['git', 'log', '-1', '--format=%h %s', fork_point],
                capture_output=True,
                text=True,
                check=True
            )

            commit_info = result2.stdout.strip()
            print(f"\n✅ 检测到fork起点: {commit_info}")

            return fork_point
        except subprocess.CalledProcessError:
            print("\n⚠️  无法自动检测fork起点")
            return None

    def fetch_upstream(self, upstream):
        """获取上游更新"""
        print(f"\n🔄 正在获取上游更新 ({upstream}/main)...")
        try:
            subprocess.run(
                ['git', 'fetch', upstream],
                check=True,
                capture_output=True
            )
            print("✅ 上游更新获取成功")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ 获取上游更新失败: {e}")
            return False

    def count_upstream_commits(self, upstream):
        """统计上游新增的提交数"""
        try:
            result = subprocess.run(
                ['git', 'rev-list', '--count', 'HEAD..', f'{upstream}/main'],
                capture_output=True,
                text=True,
                check=True
            )

            count = int(result.stdout.strip())
            print(f"📊 上游新增提交数: {count}")
            return count
        except subprocess.CalledProcessError:
            return 0

    def create_backup_branch(self):
        """创建备份分支"""
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_branch = f'backup-before-sync-{timestamp}'

        print(f"\n📦 创建备份分支: {backup_branch}")
        subprocess.run(
            ['git', 'branch', backup_branch],
            check=True
        )

        print(f"✅ 备份分支创建成功")
        return backup_branch

    def create_work_branch(self):
        """创建工作分支"""
        timestamp = datetime.now().strftime('%Y%m%d')
        work_branch = f'sync/merge-upstream-{timestamp}'

        # 检查分支是否已存在
        result = subprocess.run(
            ['git', 'branch', '--list', work_branch],
            capture_output=True,
            text=True
        )

        if result.stdout.strip():
            print(f"\n⚠️  工作分支 {work_branch} 已存在")
            response = input("是否切换到该分支继续？(yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                return None
        else:
            print(f"\n🔧 创建工作分支: {work_branch}")
            subprocess.run(
                ['git', 'checkout', '-b', work_branch],
                check=True
            )
            print(f"✅ 工作分支创建成功")

        return work_branch

    def save_config(self, config):
        """保存配置"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"\n💾 配置已保存到: {self.config_file}")

    def run(self):
        """运行初始化流程"""
        self.print_banner()

        # 1. 检查Git仓库
        if not self.check_git_repo():
            return False

        # 2. 检查工作区
        if not self.check_working_tree_clean():
            return False

        # 3. 获取当前分支
        current_branch = self.get_current_branch()

        # 4. 列出远程仓库
        remotes = self.list_remotes()

        # 5. 询问上游仓库
        upstream = self.ask_upstream(remotes)
        if not upstream:
            return False

        # 6. 获取上游更新
        if not self.fetch_upstream(upstream):
            return False

        # 7. 统计上游提交
        commit_count = self.count_upstream_commits(upstream)
        if commit_count == 0:
            print("\n✅ 上游没有新提交，无需合并")
            return True

        # 8. 检测fork起点
        fork_point = self.detect_fork_point(upstream)

        # 9. 创建备份分支
        backup_branch = self.create_backup_branch()

        # 10. 创建工作分支
        work_branch = self.create_work_branch()
        if not work_branch:
            return False

        # 11. 保存配置
        self.config = {
            'upstream': upstream,
            'fork_point': fork_point,
            'backup_branch': backup_branch,
            'work_branch': work_branch,
            'original_branch': current_branch,
            'upstream_commits': commit_count,
            'initialized_at': datetime.now().isoformat()
        }
        self.save_config(self.config)

        # 12. 显示下一步操作
        print("\n" + "=" * 80)
        print("✅ 初始化完成！")
        print("=" * 80)
        print()
        print("📋 合并信息：")
        print(f"   - 上游仓库: {upstream}")
        print(f"   - 上游新提交: {commit_count} 个")
        print(f"   - 工作分支: {work_branch}")
        print(f"   - 备份分支: {backup_branch}")
        print()
        print("📝 下一步操作：")
        print("   1. 分析差异：python analyze_upstream_diff.py")
        print("   2. 分类冲突：python classify_conflicts.py")
        print("   3. 分步合并（详见技能文档）")
        print()
        print("💡 提示：您可以随时使用以下命令回滚：")
        print(f"   git checkout {current_branch}")
        print(f"   git branch -D {work_branch}")
        print()

        return True


def main():
    """主函数"""
    initializer = RepoSyncInitializer()
    success = initializer.run()

    if success:
        print("🎉 初始化成功！现在可以开始合并流程了。")
        sys.exit(0)
    else:
        print("\n❌ 初始化失败，请检查错误信息后重试。")
        sys.exit(1)


if __name__ == '__main__':
    main()
