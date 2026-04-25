# Agent Index

> Generated file by `scripts/openclaw-ops/generate_runtime_binding_manifests.py`. Do not edit manually.

## coordinator
- name: coordinator
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-coordinator
- agentDir: None
- model: openai-codex/gpt-5.4
- allowAgentsCount: 10

## doc-writer
- name: doc-writer
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-doc-writer
- agentDir: None
- model: glmcode/glm-4.7
- allowAgentsCount: 0

## frontend-dev
- name: frontend-dev
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-frontend-dev
- agentDir: None
- model: openai-codex/gpt-5.3-codex
- allowAgentsCount: 0

## backend-dev
- name: backend-dev
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-backend-dev
- agentDir: None
- model: openai-codex/gpt-5.3-codex
- allowAgentsCount: 0

## reviewer
- name: 代码审核
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-reviewer
- agentDir: None
- model: openai-codex/gpt-5.4
- allowAgentsCount: 0

## tester
- name: 测试验收
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-tester
- agentDir: None
- model: glmcode/glm-4.7
- allowAgentsCount: 0

## deployer
- name: deployer
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-deployer
- agentDir: None
- model: glmcode/glm-4.7
- allowAgentsCount: 0

## ops-agent
- name: ops-agent
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-ops-agent
- agentDir: /home/ubuntu/.openclaw/agents/ops-agent/agent
- model: glmcode/glm-4.7
- allowAgentsCount: 1

## project-agent
- name: project-agent
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-project-agent
- agentDir: /home/ubuntu/.openclaw/agents/project-agent/agent
- model: openai-codex/gpt-5.3-codex
- allowAgentsCount: 1

## web-agent
- name: web-agent
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-web-agent
- agentDir: /home/ubuntu/.openclaw/agents/web-agent/agent
- model: glmcode/glm-4.7
- allowAgentsCount: 0
