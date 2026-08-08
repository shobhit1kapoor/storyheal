---
name: functional-verification
description: Use storyheal-cli (staff) and storyheal-widget-cli (visitor) to verify API and service changes at runtime, beyond static lint/build checks. Trigger after modifying backend API endpoints, service logic, chat flow, agent config, knowledge/RAG, workflow, or platform integration — requires local services to be running. Auto-detects changed services from git diff and runs the corresponding CLI smoke tests (system info, CRUD listing, chat e2e).
---

# functional-verification

## Purpose
Use storyheal-cli (staff) and storyheal-widget-cli (visitor) to verify API/service changes at runtime — beyond static lint/build checks.

## Trigger
After modifying backend API endpoints, service logic, chat flow, agent config, knowledge/RAG, workflow, or platform integration — when local services are running.

## Prerequisites
- Local services must be running (`make dev-all` or individual `make dev-*`)
- storyheal-cli configured (`~/.storyheal/config.json` with server + token, via `storyheal auth login`)
- storyheal-widget-cli configured (`~/.storyheal-widget/config.json`, via `storyheal-widget init`)

## What it does
1. Checks CLI build status and config availability
2. Verifies server reachability
3. Based on `git diff`, maps changed services to verification commands:

| Changed Service | Verification |
|----------------|-------------|
| storyheal-api | `storyheal system info`, `storyheal auth whoami`, `storyheal conversation list --limit 1` |
| storyheal-ai | `storyheal chat team --message "ping"`, `storyheal agent list --limit 1` |
| storyheal-rag | `storyheal knowledge list --limit 1` |
| storyheal-workflow | `storyheal workflow list --limit 1` |
| storyheal-platform | `storyheal platform list` |
| storyheal-api + visitor flow | `storyheal-widget platform info`, `storyheal-widget chat send --message "ping" --no-stream` |

4. Outputs pass/fail per check

## Usage
```bash
# Auto-detect from git diff
bash .skills/functional-verification/scripts/verify.sh

# Target specific service
bash .skills/functional-verification/scripts/verify.sh storyheal-api

# Full smoke test (all checks)
bash .skills/functional-verification/scripts/verify.sh --all
```

## Manual verification commands

### Staff-side (storyheal-cli)
```bash
StoryHeal_CLI="node repos/storyheal-cli/dist/index.js"

# System health
$StoryHeal_CLI system info
$StoryHeal_CLI auth whoami

# Chat e2e (sends to AI, gets response)
$StoryHeal_CLI chat team --message "say ok"

# CRUD verification
$StoryHeal_CLI agent list
$StoryHeal_CLI provider list
$StoryHeal_CLI knowledge list
$StoryHeal_CLI workflow list
$StoryHeal_CLI conversation list --limit 1
$StoryHeal_CLI visitor list --limit 1
$StoryHeal_CLI platform list
$StoryHeal_CLI staff list
```

### Visitor-side (storyheal-widget-cli)
```bash
WIDGET_CLI="node repos/storyheal-widget-cli/dist/index.js"

# Platform & channel
$WIDGET_CLI platform info
$WIDGET_CLI channel info

# Chat e2e (visitor sends, AI responds via SSE)
$WIDGET_CLI chat send --message "say ok" --no-stream

# History
$WIDGET_CLI chat history --limit 3
```
