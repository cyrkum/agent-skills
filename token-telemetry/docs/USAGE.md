# Usage

Set `TOKEN_TELEMETRY_DIR` to override runtime storage. The default is `~/.agents/data/token-telemetry`.

## Task lifecycle

```sh
telemetry.py init --task-id TASK
ollama_adapter.py generate --task-id TASK --model MODEL --prompt "..."
telemetry.py finalize --task-id TASK --status passed
report.py --task-id TASK
```

For retries, pass `--parent-invocation INVOCATION_ID` and `--retry-count N`.

## Baselines

```sh
telemetry.py baseline --task-id TASK --remote-tokens 10000 \
  --task-type "code-change" --model "remote-model" --prompt-version "v1"
```

Baseline values must be measured. Estimated values are not accepted by the default CLI.
