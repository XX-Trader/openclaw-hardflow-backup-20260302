# OpenClaw Hardflow Backup

This repository is a private backup of local OpenClaw hardflow workflow artifacts.

## Included
- openclaw/.workflow
- openclaw/agents (sessions excluded)
- openclaw/cron
- openclaw/ops
- openclaw/workspace (without .git)
- openclaw/skills and skills_deleted_archive
- openclaw/openclaw-workflow-latest
- claude/skills, claude/agents
- cc-switch/skills
- codex/skills

## Security handling
- Secret-bearing files are excluded from commit.
- Redacted examples are provided:
  - openclaw/openclaw.json.example
  - openclaw/agents/main/agent/models.json.example

## Project-scoped OpenClaw assets
- project-openclaw/.claude/hardflow
- project-openclaw/.claude/hardflow-lobster
- project-openclaw/scripts/hardflow
- project-openclaw/scripts/openclaw-ops
