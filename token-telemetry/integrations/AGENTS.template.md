# Token telemetry integration template

Before executing a user task:

1. Generate a unique task identifier.
2. Run `python3 ~/.agents/skills/token-telemetry/scripts/telemetry.py init --task-id "$TASK_ID"`.
3. For each local Ollama delegation, propagate `--task-id "$TASK_ID"` to `ollama_adapter.py`.
4. Before the final response, run `telemetry.py finalize --task-id "$TASK_ID" --status passed|failed`.
5. Run `python3 ~/.agents/skills/token-telemetry/scripts/report.py --task-id "$TASK_ID"` and append its text to the final response, not just tool output. Report any finalization or report-generation error.

Use resolved absolute paths if the agents home differs. This instruction fallback does not guarantee lifecycle automation.
