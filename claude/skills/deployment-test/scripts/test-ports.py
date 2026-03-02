#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
端口检测测试
用法: python test-ports.py
"""

import socket
import time
import json
import sys
from pathlib import Path


def check_port(host, port, timeout=5):
    """检查端口是否监听"""
    try:
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        response_time = int((time.time() - start_time) * 1000)

        if result == 0:
            return True, response_time
        else:
            return False, response_time
    except Exception as e:
        return False, 0


def run_tests(config=None):
    """运行端口检测测试"""
    if config is None:
        # 尝试加载配置文件
        config_paths = ['test.config.json', '../test.config.json', '../../test.config.json']
        config = None
        for path in config_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                break
            except:
                continue

        if config is None:
            print("❌ 未找到配置文件 test.config.json")
            print("使用默认配置...")
            config = {
                "services": {
                    "mysql": {"enabled": True, "host": "127.0.0.1", "port": 3306},
                    "redis": {"enabled": True, "host": "127.0.0.1", "port": 6379},
                    "backend": {"enabled": True, "host": "127.0.0.1", "port": 8000},
                    "frontend": {"enabled": True, "host": "127.0.0.1", "port": 8083}
                }
            }

    services = config.get('services', {})
    results = []
    failures = []

    print("   端口检测中...")
    print()

    # 检测 MySQL
    if services.get('mysql', {}).get('enabled', False):
        host = services.get('mysql', {}).get('host', '127.0.0.1')
        port = services.get('mysql', {}).get('port', 3306)
        timeout = services.get('mysql', {}).get('timeout', 5000) / 1000

        is_open, response_time = check_port(host, port, timeout)
        status = "✅ 正常" if is_open else "❌ 未监听"

        result = {
            "service": "MySQL",
            "port": port,
            "status": status,
            "response_time": f"{response_time}ms",
            "remark": "数据库服务" if is_open else "请检查 MySQL 服务"
        }
        results.append(result)

        if not is_open:
            failures.append({
                "service": "MySQL",
                "reason": f"端口 {port} 未监听"
            })

        print(f"   MySQL ({host}:{port})... {status}")

    # 检测 Redis
    if services.get('redis', {}).get('enabled', False):
        host = services.get('redis', {}).get('host', '127.0.0.1')
        port = services.get('redis', {}).get('port', 6379)
        timeout = services.get('redis', {}).get('timeout', 5000) / 1000

        is_open, response_time = check_port(host, port, timeout)
        status = "✅ 正常" if is_open else "❌ 未监听"

        result = {
            "service": "Redis",
            "port": port,
            "status": status,
            "response_time": f"{response_time}ms",
            "remark": "缓存服务" if is_open else "请检查 Redis 服务"
        }
        results.append(result)

        if not is_open:
            failures.append({
                "service": "Redis",
                "reason": f"端口 {port} 未监听"
            })

        print(f"   Redis ({host}:{port})... {status}")

    # 检测后端服务
    if services.get('backend', {}).get('enabled', False):
        backend_config = services.get('backend', {})
        if 'url' in backend_config:
            # 从 URL 解析主机和端口
            from urllib.parse import urlparse
            parsed = urlparse(backend_config['url'])
            host = parsed.hostname or '127.0.0.1'
            port = parsed.port or 8000
        else:
            host = backend_config.get('host', '127.0.0.1')
            port = backend_config.get('port', 8000)

        timeout = backend_config.get('timeout', 10000) / 1000

        is_open, response_time = check_port(host, port, timeout)
        status = "✅ 正常" if is_open else "❌ 未监听"

        result = {
            "service": "Backend",
            "port": port,
            "status": status,
            "response_time": f"{response_time}ms",
            "remark": "后端 API 服务" if is_open else "请检查后端服务"
        }
        results.append(result)

        if not is_open:
            failures.append({
                "service": "Backend",
                "reason": f"端口 {port} 未监听"
            })

        print(f"   Backend ({host}:{port})... {status}")

    # 检测前端服务
    if services.get('frontend', {}).get('enabled', False):
        frontend_config = services.get('frontend', {})
        if 'url' in frontend_config:
            # 从 URL 解析主机和端口
            from urllib.parse import urlparse
            parsed = urlparse(frontend_config['url'])
            host = parsed.hostname or '127.0.0.1'
            port = parsed.port or 8083
        else:
            host = frontend_config.get('host', '127.0.0.1')
            port = frontend_config.get('port', 8083)

        timeout = frontend_config.get('timeout', 10000) / 1000

        is_open, response_time = check_port(host, port, timeout)
        status = "✅ 正常" if is_open else "❌ 未监听"

        result = {
            "service": "Frontend",
            "port": port,
            "status": status,
            "response_time": f"{response_time}ms",
            "remark": "前端 Web 服务" if is_open else "请检查前端服务"
        }
        results.append(result)

        if not is_open:
            failures.append({
                "service": "Frontend",
                "reason": f"端口 {port} 未监听"
            })

        print(f"   Frontend ({host}:{port})... {status}")

    print()

    # 构建详情
    details = "所有服务端口检测完成。"
    if failures:
        details += f"\n\n失败服务: {', '.join([f['service'] for f in failures])}"

    return {
        "results": results,
        "failures": failures,
        "details": details
    }


if __name__ == '__main__':
    print("=" * 60)
    print("  端口检测测试")
    print("=" * 60)
    print()

    results = run_tests()

    print()
    print("=" * 60)
    print("  检测完成")
    print("=" * 60)
    print()

    passed = sum(1 for r in results['results'] if '✅' in r['status'])
    total = len(results['results'])

    print(f"总计: {total}")
    print(f"通过: {passed}")
    print(f"失败: {total - passed}")
    print()

    if results['failures']:
        print("❌ 存在服务未启动")
        for failure in results['failures']:
            print(f"   - {failure['service']}: {failure['reason']}")
        sys.exit(1)
    else:
        print("✅ 所有服务端口正常")
        sys.exit(0)
