# Runtime Skills

- 清单文件：`skills/library/openclaw-workflow-manager/scripts/runtime-required-skills.json`
- 补齐入口：`ensure_runtime_skills.py`
- 安装入口：仓库根目录 `setup.py`

```bash
python skills/library/openclaw-workflow-manager/scripts/ensure_runtime_skills.py \
  --manifest skills/library/openclaw-workflow-manager/scripts/runtime-required-skills.json \
  --help

python setup.py --runtime-home <RUNTIME_HOME> --runtime-name <RUNTIME_NAME> --dry-run --emit-json
```

清单记录所需 Skill 和命令；安装器负责把 owner 脚本复制到目标 Runtime。新增依赖时同步更新清单、安装器映射和定向测试。
