#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API 接口测试
用法: python test-api.py
"""

import requests
import json
import sys
import time


def run_tests(config=None):
    """运行 API 测试"""
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
                    "backend": {"url": "http://localhost:8000"}
                },
                "apiEndpoints": [
                    {
                        "name": "用户登录",
                        "method": "POST",
                        "path": "/api/accounts/login/",
                        "body": {"email": "test@example.com", "password": "Test123456"},
                        "expectedStatus": 200,
                        "expectedCode": 200
                    }
                ]
            }

    backend_url = config.get('services', {}).get('backend', {}).get('url', 'http://localhost:8000')
    endpoints = config.get('apiEndpoints', [])
    test_accounts = config.get('testAccounts', {})

    results = []
    failures = []
    success_text = ""

    print("   API 测试中...")
    print()

    session = requests.Session()

    for endpoint in endpoints:
        name = endpoint.get('name', 'Unknown')
        method = endpoint.get('method', 'GET')
        path = endpoint.get('path', '')
        expected_status = endpoint.get('expectedStatus', 200)
        expected_code = endpoint.get('expectedCode', 200)

        # 构造请求
        url = f"{backend_url}{path}"
        body = endpoint.get('body', {})
        headers = endpoint.get('headers', {})

        # 替换占位符
        if isinstance(body, dict):
            if 'email' in test_accounts:
                body = {k: v.replace('{{email}}', test_accounts['email']) if isinstance(v, str) else v for k, v in body.items()}
            if 'password' in test_accounts:
                body = {k: v.replace('{{password}}', test_accounts['password']) if isinstance(v, str) else v for k, v in body.items()}

        try:
            start_time = time.time()
            if method.upper() == 'GET':
                response = session.get(url, headers=headers, timeout=10)
            elif method.upper() == 'POST':
                response = session.post(url, json=body, headers=headers, timeout=10)
            elif method.upper() == 'PUT':
                response = session.put(url, json=body, headers=headers, timeout=10)
            elif method.upper() == 'DELETE':
                response = session.delete(url, json=body, headers=headers, timeout=10)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")

            response_time = int((time.time() - start_time) * 1000)

            # 获取响应数据
            try:
                response_data = response.json()
                actual_code = response_data.get('code', None)
            except:
                response_data = None
                actual_code = None

            # 验证结果
            status_match = response.status_code == expected_status
            code_match = actual_code == expected_code if expected_code else True

            if status_match and code_match:
                result = "✅"
                print(f"   ✅ {name} ({response_time}ms)")
            else:
                result = "❌"
                failure_reason = []
                if not status_match:
                    failure_reason.append(f"状态码: 预期 {expected_status}, 实际 {response.status_code}")
                if not code_match:
                    failure_reason.append(f"响应码: 预期 {expected_code}, 实际 {actual_code}")

                failures.append({
                    "name": name,
                    "reason": ", ".join(failure_reason),
                    "details": str(response_data)[:200] if response_data else response.text[:200]
                })
                print(f"   ❌ {name}: {', '.join(failure_reason)}")

            results.append({
                "name": name,
                "method": method,
                "path": path,
                "expectedStatus": expected_status,
                "actualStatus": response.status_code,
                "expectedCode": expected_code,
                "actualCode": actual_code or '-',
                "result": result,
                "responseTime": f"{response_time}ms"
            })

            # 记录成功示例
            if result == "✅" and not success_text:
                success_text = f"""
### {name}

**请求**:
```
{method} {url}
```

**响应**:
```json
{json.dumps(response_data, indent=2, ensure_ascii=False)}
```

"""

        except Exception as e:
            results.append({
                "name": name,
                "method": method,
                "path": path,
                "expectedStatus": expected_status,
                "actualStatus": "-",
                "expectedCode": expected_code,
                "actualCode": "-",
                "result": "❌",
                "responseTime": "-"
            })
            failures.append({
                "name": name,
                "reason": "请求失败",
                "details": str(e)
            })
            print(f"   ❌ {name}: {str(e)}")

    print()

    # 构建失败详情文本
    failures_text = ""
    if failures:
        for failure in failures:
            failures_text += f"- **{failure['name']}**: {failure['reason']}\n"
            if failure.get('details'):
                failures_text += f"  错误信息: `{failure['details']}`\n\n"

    return {
        "results": results,
        "failures": failures,
        "failures_text": failures_text or "无",
        "success_text": success_text or "无"
    }


if __name__ == '__main__':
    print("=" * 60)
    print("  API 接口测试")
    print("=" * 60)
    print()

    results = run_tests()

    print()
    print("=" * 60)
    print("  测试完成")
    print("=" * 60)
    print()

    passed = sum(1 for r in results['results'] if r['result'] == '✅')
    total = len(results['results'])

    print(f"总计: {total}")
    print(f"通过: {passed}")
    print(f"失败: {total - passed}")
    print()

    if results['failures']:
        print("❌ 存在 API 测试失败")
        for failure in results['failures']:
            print(f"   - {failure['name']}: {failure['reason']}")
        sys.exit(1)
    else:
        print("✅ 所有 API 测试通过")
        sys.exit(0)
