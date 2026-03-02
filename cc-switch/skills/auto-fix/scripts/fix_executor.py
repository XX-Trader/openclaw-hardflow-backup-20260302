#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复执行器

执行具体的修复操作
"""

import os
import re
import json
from pathlib import Path


class FixExecutor:
    """修复执行器"""

    def __init__(self, config, git_manager):
        self.config = config
        self.git = git_manager

        # 项目路径
        self.project_root = Path(config["project"]["root"])
        self.backend_path = Path(config["project"]["backendPath"])
        self.frontend_path = Path(config["project"]["frontendPath"])

    def fix(self, problem):
        """
        执行修复

        Args:
            problem: 问题对象

        Returns:
            修复结果 (success: bool, message: str)
        """
        print(f"\n🔧 修复问题: {problem.title}")
        print(f"   类别: {problem.category}")
        print(f"   严重级别: {problem.severity}")

        # 根据问题类型选择修复器
        fixer_map = {
            "config": self.fix_config,
            "database": self.fix_database,
            "api": self.fix_api,
            "auth": self.fix_auth,
            "frontend": self.fix_frontend
        }

        fixer = fixer_map.get(problem.category)

        if not fixer:
            return {
                "success": False,
                "message": f"未知的问题类别: {problem.category}"
            }

        # 执行修复
        try:
            result = fixer(problem)

            # 如果修复成功，提交更改
            if result["success"]:
                commit_msg = f"{problem.title}: {result['message']}"
                self.git.commit(problem.category, commit_msg)
                print(f"✅ 已提交修复: {commit_msg}")

            return result

        except Exception as e:
            return {
                "success": False,
                "message": f"修复失败: {str(e)}"
            }

    def fix_config(self, problem):
        """修复配置问题"""
        service = problem.details.get("service", "")

        if "端口" in problem.title:
            return self._fix_port_config(service, problem)
        elif "URL" in problem.title or "域名" in problem.title:
            return self._fix_url_config(problem)
        elif "环境变量" in problem.title:
            return self._fix_env_config(problem)
        else:
            return {
                "success": False,
                "message": f"未知配置问题类型: {problem.title}"
            }

    def _fix_port_config(self, service, problem):
        """修复端口配置"""
        print(f"   修复 {service} 端口配置...")

        # 读取配置文件
        config_files = [
            self.backend_path / ".env.local",
            self.backend_path / ".env",
            self.project_root / ".env.local"
        ]

        config_file = None
        for f in config_files:
            if f.exists():
                config_file = f
                break

        if not config_file:
            return {
                "success": False,
                "message": "未找到配置文件"
            }

        # 读取配置
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 根据服务类型确定端口配置
        port_map = {
            "MySQL": ("MYSQL_HOST", "MYSQL_PORT"),
            "Redis": ("REDIS_HOST", "REDIS_PORT"),
            "Django": ("DJANGO_HOST", "DJANGO_PORT"),
            "Vue": ("VUE_HOST", "VUE_PORT")
        }

        if service not in port_map:
            return {
                "success": False,
                "message": f"未知服务类型: {service}"
            }

        host_key, port_key = port_map[service]

        # 检查配置是否存在
        if host_key not in content and port_key not in content:
            # 需要添加配置
            with open(config_file, 'a', encoding='utf-8') as f:
                f.write(f"\n# Auto-Fix: {service} 端口配置\n")
                f.write(f"{host_key}=127.0.0.1\n")
                f.write(f"{port_key}=3306\n" if service == "MySQL" else f"{port_key}=6379\n")

            return {
                "success": True,
                "message": f"已添加 {service} 端口配置"
            }

        return {
            "success": True,
            "message": f"{service} 端口配置正常"
        }

    def _fix_url_config(self, problem):
        """修复URL/域名配置"""
        print(f"   修复 URL 配置...")

        # 读取前端配置文件
        config_files = [
            self.frontend_path / "src" / "apis" / "base.js",
            self.frontend_path / ".env.local",
            self.frontend_path / "vite.config.js"
        ]

        for config_file in config_files:
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 检查是否有硬编码的域名
                if "localhost" in content or "127.0.0.1" in content:
                    # 替换为正确的域名
                    content = content.replace("localhost:8000", "api.example.com")
                    content = content.replace("127.0.0.1:8000", "api.example.com")

                    with open(config_file, 'w', encoding='utf-8') as f:
                        f.write(content)

                    return {
                        "success": True,
                        "message": f"已更新 URL 配置: {config_file.name}"
                    }

        return {
            "success": False,
            "message": "未找到 URL 配置文件"
        }

    def _fix_env_config(self, problem):
        """修复环境变量配置"""
        print(f"   修复环境变量配置...")

        env_file = self.backend_path / ".env.local"

        if not env_file.exists():
            # 创建 .env.local 文件
            env_file.parent.mkdir(parents=True, exist_ok=True)

            with open(env_file, 'w', encoding='utf-8') as f:
                f.write("# Auto-Fix: 环境变量配置\n")
                f.write("DJANGO_SECRET_KEY=your-secret-key-here\n")
                f.write("DJANGO_DEBUG=False\n")
                f.write("DATABASE_URL=mysql://user:password@localhost/dbname\n")

            return {
                "success": True,
                "message": "已创建 .env.local 文件"
            }

        return {
            "success": True,
            "message": "环境变量配置正常"
        }

    def fix_database(self, problem):
        """修复数据库问题"""
        print(f"   修复数据库问题...")

        if "字段" in problem.description and "缺失" in problem.description:
            return self._fix_missing_field(problem)
        elif "迁移" in problem.description:
            return self._fix_migration(problem)
        elif "表" in problem.description and "不存在" in problem.description:
            return self._fix_missing_table(problem)
        else:
            return {
                "success": False,
                "message": f"未知数据库问题: {problem.description}",
                "needs_planning": True
            }

    def _fix_missing_field(self, problem):
        """修复缺失字段"""
        print(f"   检测缺失字段...")

        # 从问题描述中提取字段信息
        # 示例: "字段 'wallet_address' 在表 'pm_bot_config' 中缺失"

        import re
        match = re.search(r"字段\s+['\"](\w+)['\"]\s+在表\s+['\"](\w+)['\"]", problem.description)

        if not match:
            return {
                "success": False,
                "message": "无法解析字段信息",
                "needs_planning": True
            }

        field_name = match.group(1)
        table_name = match.group(2)

        print(f"   缺失字段: {field_name} (表: {table_name})")

        # 查找对应的模型文件
        models_dir = self.backend_path / "pm_robot" / "models"

        if not models_dir.exists():
            return {
                "success": False,
                "message": "未找到 models 目录",
                "needs_planning": True
            }

        # 查找模型文件
        model_files = list(models_dir.glob("*_models.py"))

        for model_file in model_files:
            with open(model_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 检查是否包含对应的表
            if table_name in content or table_name.replace('_', '').lower() in content.lower():
                # 生成迁移文件
                print(f"   生成迁移: 添加字段 {field_name}")

                migration_content = f"""# Generated by Auto-Fix
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pm_robot', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='{table_name.replace('pm_', '').replace('user_', '')}',
            name='{field_name}',
            field=models.{self._guess_field_type(field_name)}(null=True, blank=True),
        ),
    ]
"""

                # 创建迁移文件
                migrations_dir = self.backend_path / "pm_robot" / "migrations"
                migrations_dir.mkdir(parents=True, exist_ok=True)

                migration_file = migrations_dir / f"auto_fix_add_{field_name}.py"
                with open(migration_file, 'w', encoding='utf-8') as f:
                    f.write(migration_content)

                return {
                    "success": True,
                    "message": f"已生成迁移文件: {migration_file.name}"
                }

        return {
            "success": False,
            "message": f"未找到表 {table_name} 对应的模型文件",
            "needs_planning": True
        }

    def _guess_field_type(self, field_name):
        """根据字段名猜测字段类型"""
        if "address" in field_name:
            return "CharField(max_length=255)"
        elif "balance" in field_name or "amount" in field_name:
            return "DecimalField(max_digits=20, decimal_places=8)"
        elif "status" in field_name:
            return "IntegerField"
        elif "time" in field_name or "date" in field_name:
            return "DateTimeField"
        elif "key" in field_name or "secret" in field_name:
            return "CharField(max_length=255)"
        else:
            return "CharField(max_length=255)"

    def _fix_migration(self, problem):
        """修复迁移问题"""
        print(f"   运行数据库迁移...")

        import subprocess

        # 运行 makemigrations
        result = subprocess.run(
            ["python", "manage.py", "makemigrations"],
            capture_output=True,
            text=True,
            cwd=self.backend_path
        )

        if result.returncode != 0:
            return {
                "success": False,
                "message": f"makemigrations 失败: {result.stderr}",
                "needs_planning": True
            }

        # 运行 migrate
        result = subprocess.run(
            ["python", "manage.py", "migrate"],
            capture_output=True,
            text=True,
            cwd=self.backend_path
        )

        if result.returncode != 0:
            return {
                "success": False,
                "message": f"migrate 失败: {result.stderr}",
                "needs_planning": True
            }

        return {
            "success": True,
            "message": "数据库迁移完成"
        }

    def _fix_missing_table(self, problem):
        """修复缺失表"""
        print(f"   创建缺失表...")

        # 这个通常需要人工设计，返回需要规划
        return {
            "success": False,
            "message": "缺失表需要人工设计表结构",
            "needs_planning": True
        }

    def fix_api(self, problem):
        """修复 API 问题"""
        print(f"   修复 API 问题...")

        if "404" in problem.description:
            return self._fix_api_404(problem)
        elif "状态码" in problem.description:
            return self._fix_api_status_code(problem)
        elif "参数" in problem.description:
            return self._fix_api_params(problem)
        else:
            return {
                "success": False,
                "message": f"未知 API 问题: {problem.description}",
                "needs_planning": True
            }

    def _fix_api_404(self, problem):
        """修复 API 404 错误"""
        print(f"   检测 404 错误...")

        # 从描述中提取 API 路径
        match = re.search(r"(/api/[^\s:]+)", problem.description)

        if not match:
            return {
                "success": False,
                "message": "无法解析 API 路径",
                "needs_planning": True
            }

        api_path = match.group(1)
        print(f"   缺失 API: {api_path}")

        # 检查路由是否在 urls.py 中定义
        urls_file = self.backend_path / "pm_robot" / "urls.py"

        if not urls_file.exists():
            return {
                "success": False,
                "message": "未找到 urls.py",
                "needs_planning": True
            }

        with open(urls_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查是否包含该路径
        if api_path not in content:
            # 添加路由
            print(f"   添加路由: {api_path}")

            # 生成视图函数模板
            view_content = f"""
# Auto-Fix: 新增 API 接口
@require_http_methods(["POST", "GET"])
def auto_fix_view(request):
    \"\"\"Auto-Fix 自动生成的视图\"\"\"
    if request.method == "POST":
        data = json.loads(request.body)
        # TODO: 实现业务逻辑
        return JsonResponse({{"code": 200, "msg": "success", "data": {{}}}})
    else:
        # TODO: 实现 GET 逻辑
        return JsonResponse({{"code": 200, "msg": "success", "data": {{}}}})
"""

            # 写入视图文件
            views_file = self.backend_path / "pm_robot" / "views" / "auto_fix_views.py"
            with open(views_file, 'a', encoding='utf-8') as f:
                f.write(view_content)

            # 更新 urls.py
            import_line = "from pm_robot.views.auto_fix_views import auto_fix_view\n"

            if import_line not in content:
                content = content + "\n" + import_line

            # 添加路由
            route_line = f"    path('{api_path.replace('/api/pm-robot/', '')}', views.auto_fix_view, name='auto_fix'),\n"

            # 找到 urlpatterns 并添加
            if "urlpatterns = [" in content:
                content = content.replace(
                    "urlpatterns = [",
                    "urlpatterns = [\n" + route_line
                )

            with open(urls_file, 'w', encoding='utf-8') as f:
                f.write(content)

            return {
                "success": True,
                "message": f"已添加 API 路由: {api_path}"
            }

        return {
            "success": False,
            "message": f"API 路由已存在但仍 404，需要检查视图实现",
            "needs_planning": True
        }

    def _fix_api_status_code(self, problem):
        """修复 API 状态码错误"""
        print(f"   修复状态码错误...")

        # 从描述中提取信息
        # 示例: "状态码: 预期 200, 实际 404"

        match = re.search(r"预期\s+(\d+),\s+实际\s+(\d+)", problem.description)

        if not match:
            return {
                "success": False,
                "message": "无法解析状态码信息",
                "needs_planning": True
            }

        expected = match.group(1)
        actual = match.group(2)

        print(f"   状态码不匹配: 预期 {expected}, 实际 {actual}")

        # 状态码问题通常需要人工分析
        return {
            "success": False,
            "message": f"状态码 {actual} 需要人工分析",
            "needs_planning": True
        }

    def _fix_api_params(self, problem):
        """修复 API 参数错误"""
        print(f"   修复参数错误...")

        # 参数错误通常需要人工分析
        return {
            "success": False,
            "message": "API 参数错误需要人工分析",
            "needs_planning": True
        }

    def fix_auth(self, problem):
        """修复认证问题"""
        print(f"   修复认证问题...")

        if "权限" in problem.description:
            return self._fix_permission(problem)
        elif "认证" in problem.description:
            return self._fix_authentication(problem)
        else:
            return {
                "success": False,
                "message": f"未知认证问题: {problem.description}",
                "needs_planning": True
            }

    def _fix_permission(self, problem):
        """修复权限问题"""
        print(f"   修复权限问题...")

        # 权限问题通常需要人工分析
        return {
            "success": False,
            "message": "权限配置需要人工分析",
            "needs_planning": True
        }

    def _fix_authentication(self, problem):
        """修复认证问题"""
        print(f"   修复认证问题...")

        # 认证问题通常需要人工分析
        return {
            "success": False,
            "message": "认证配置需要人工分析",
            "needs_planning": True
        }

    def fix_frontend(self, problem):
        """修复前端问题"""
        print(f"   修复前端问题...")

        if "组件" in problem.description and "导入" in problem.description:
            return self._fix_component_import(problem)
        elif "选择器" in problem.description or "selector" in problem.description.lower():
            return self._fix_selector(problem)
        elif "渲染" in problem.description:
            return self._fix_rendering(problem)
        else:
            return {
                "success": False,
                "message": f"未知前端问题: {problem.description}",
                "needs_planning": True
            }

    def _fix_component_import(self, problem):
        """修复组件导入错误"""
        print(f"   修复组件导入...")

        # 从描述中提取组件名
        match = re.search(r"['\"](\w+)['\"]", problem.description)

        if not match:
            return {
                "success": False,
                "message": "无法解析组件名",
                "needs_planning": True
            }

        component_name = match.group(1)
        print(f"   缺失组件: {component_name}")

        # 搜索组件
        src_dir = self.frontend_path / "src"
        component_files = list(src_dir.rglob(f"{component_name}.vue"))

        if not component_files:
            return {
                "success": False,
                "message": f"未找到组件: {component_name}",
                "needs_planning": True
            }

        # 找到了组件，检查导入路径
        component_file = component_files[0]
        print(f"   找到组件: {component_file}")

        # 检查哪个文件导入了该组件
        vue_files = list(src_dir.rglob("*.vue"))

        for vue_file in vue_files:
            with open(vue_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 检查是否有错误的导入
            if component_name in content and "from" in content:
                # 检查导入路径是否正确
                import_match = re.search(r"from\s+['\"](.+)['\"]", content)

                if import_match:
                    import_path = import_match.group(1)

                    # 计算正确的导入路径
                    relative_path = os.path.relpath(component_file.parent, vue_file.parent)

                    if relative_path == ".":
                        correct_import = f"./{component_file.name}"
                    else:
                        correct_import = f"./{relative_path.replace(os.sep, '/')}/{component_file.name}"

                    # 替换错误的导入
                    content = content.replace(import_path, correct_import)

                    with open(vue_file, 'w', encoding='utf-8') as f:
                        f.write(content)

                    return {
                        "success": True,
                        "message": f"已修复导入路径: {vue_file.name}"
                    }

        return {
            "success": False,
            "message": "未找到需要修复的导入",
            "needs_planning": True
        }

    def _fix_selector(self, problem):
        """修复选择器错误"""
        print(f"   修复选择器...")

        # 选择器问题通常需要人工分析
        return {
            "success": False,
            "message": "选择器错误需要人工分析",
            "needs_planning": True
        }

    def _fix_rendering(self, problem):
        """修复渲染问题"""
        print(f"   修复渲染问题...")

        # 渲染问题通常需要人工分析
        return {
            "success": False,
            "message": "渲染错误需要人工分析",
            "needs_planning": True
        }
