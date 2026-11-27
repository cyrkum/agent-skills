---
name: token-telemetry
description: Collect, normalize, and report AI agent token usage across local and remote model invocations.
---

# Token telemetry

Use this skill to initialize telemetry before a user task, append each model invocation, finalize the task, and generate a compact end-of-task report.

The runtime defaults to `~/.agents/data/token-telemetry/`. It uses JSON Lines and stores no prompt or generated content.

```sh
skill_dir="$HOME/.agents/skills/token-telemetry"
python3 "$skill_dir/scripts/telemetry.py" init --task-id TASK
python3 "$skill_dir/scripts/ollama_adapter.py" generate --task-id TASK --model MODEL --prompt "Prompt"
python3 "$skill_dir/scripts/telemetry.py" finalize --task-id TASK --status passed
python3 "$skill_dir/scripts/report.py" --task-id TASK
```

Remote usage is optional. Unavailable measurements remain `null`; no KPI is fabricated. For instruction-based integration, follow [integrations/AGENTS.template.md](integrations/AGENTS.template.md).
