# Agent Index

## main
- name: 大总管
- default: True
- workspace: /home/ubuntu/.openclaw/workspace
- agentDir: None
- model: glmcode/glm-5
- allowAgentsCount: 12

## coordinator
- name: coordinator
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-coordinator
- agentDir: None
- model: glmcode/glm-5
- allowAgentsCount: 12

## doc-writer
- name: doc-writer
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-doc-writer
- agentDir: None
- model: glmcode/glm-5
- allowAgentsCount: 0

## frontend-dev
- name: frontend-dev
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-frontend-dev
- agentDir: None
- model: glmcode/glm-5
- allowAgentsCount: 0

## backend-dev
- name: backend-dev
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-backend-dev
- agentDir: None
- model: glmcode/glm-5
- allowAgentsCount: 0

## reviewer
- name: 代码审核
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-reviewer
- agentDir: None
- model: glmcode/glm-5
- allowAgentsCount: 0

## tester
- name: 测试验收
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-tester
- agentDir: None
- model: glmcode/glm-5
- allowAgentsCount: 0

## deployer
- name: deployer
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-deployer
- agentDir: None
- model: glmcode/glm-5
- allowAgentsCount: 0

## agent-factory
- name: agent-factory
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-agent-factory
- agentDir: None
- model: glmcode/glm-5
- allowAgentsCount: 2

## ops-agent
- name: ops-agent
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-ops-agent
- agentDir: /home/ubuntu/.openclaw/agents/ops-agent/agent
- model: glmcode/glm-4.7
- allowAgentsCount: 2

## optimize-agent
- name: optimize-agent
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-optimize-agent
- agentDir: /home/ubuntu/.openclaw/agents/optimize-agent/agent
- model: glmcode/glm-5
- allowAgentsCount: 1

## project-agent
- name: project-agent
- default: False
- workspace: /home/ubuntu/.openclaw/workspace-project-agent
- agentDir: /home/ubuntu/.openclaw/agents/project-agent/agent
- model: glmcode/glm-5
- allowAgentsCount: 0

