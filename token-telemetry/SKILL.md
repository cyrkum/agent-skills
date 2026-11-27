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

Before the final response, finalize the task with its actual status and run the
report. Include the report's text in the final response itself, after the task
result; tool output alone may not be visible in chat (including VS Code).
If finalization or report generation fails, report the error instead of
claiming telemetry was shown.

For Ollama visible thinking-token counts, add `--count-reasoning`. Capture
Copilot SDK `assistant.usage` events or record other measured usage with
`telemetry.py record`; see [usage](docs/USAGE.md). Reports calculate missing totals or components when the
other two counts are known and show the available measurements. Truly
unavailable measurements remain `null`/`N/A`; zeros are reported only when
measured or calculated. No KPI is fabricated. For instruction-based integration,
follow [integrations/AGENTS.template.md](integrations/AGENTS.template.md).
