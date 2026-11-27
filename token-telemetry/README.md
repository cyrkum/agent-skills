# token-telemetry

`token-telemetry` is a model-agnostic, portable telemetry skill for agent tasks. It records normalized invocation metadata in JSON Lines, calculates common delegation KPIs, and produces compact reports.

## Quick start

```sh
./scripts/install.sh --source "$(pwd)" --agents-home "$HOME/.agents"
python3 scripts/telemetry.py init --task-id demo
python3 scripts/ollama_adapter.py generate --task-id demo --model qwen3.5:9b-q4_K_M --prompt "Reply with OK"
python3 scripts/telemetry.py finalize --task-id demo --status passed
python3 scripts/report.py --task-id demo
```

No baseline or remote telemetry is required. Reports identify unavailable KPIs explicitly.
Measured usage from other providers can be recorded with `telemetry.py record`;
see [usage](docs/USAGE.md).

## Components

- `scripts/telemetry.py`: task lifecycle, persistence, and baselines
- `scripts/ollama_adapter.py`: native Ollama `/api/generate` telemetry
- `scripts/copilot_adapter.py`: Copilot SDK `assistant.usage` event collection
- `scripts/kpi.py`: RTR, TDR, TAF, RTS, TSR, and TCR
- `scripts/report.py`: compact human-readable report
- `schemas/telemetry.schema.json`: versioned normalized record
- `integrations/`: instruction and host integration templates
- `tests/`: synthetic unit and integration fixtures
