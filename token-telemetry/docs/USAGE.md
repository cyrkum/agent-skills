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

## Ollama reasoning and cached tokens

Ollama returns `prompt_eval_cached_count` in its
[usage metadata](https://docs.ollama.com/api/usage); it is recorded when
present. To additionally count visible reasoning tokens, request logprobs:

```sh
ollama_adapter.py chat --task-id TASK --model MODEL --message "..." \
  --stream --count-reasoning
```

Ollama [separates thinking text](https://docs.ollama.com/capabilities/thinking)
and exposes output-token logprobs. The adapter joins streamed thinking fragments
and counts the exact, uniquely token-aligned matching span in those logprobs.
This is the count of **visible thinking text**, not a provider-reported total
of all internal reasoning/control tokens. It is marked in `derived_fields`.
Requests with `--count-reasoning` may cost more time or be unsupported by some
models. If thinking text or logprobs are absent, mismatched, or ambiguous, the
adapter warns and leaves the count unavailable. The text and logprobs are held
only in memory, never written to telemetry.

## Copilot SDK usage events

The [Copilot SDK](https://github.com/github/copilot-sdk/blob/main/docs/features/usage-and-billing.md)
emits an `assistant.usage` event for each model call. Subscribe in the SDK
application **before** sending the task; events are ephemeral and are not
replayed on resume. For an application whose calls all use remote Copilot:

```python
import sys
sys.path.insert(0, "/absolute/path/to/token-telemetry/scripts")
from copilot.session_events import SessionEventType
from copilot_adapter import record_usage

def on_event(event):
    if event.type == SessionEventType.ASSISTANT_USAGE:
        record_usage(event.data, TASK_ID, location="remote")

session.on(on_event)
```

For mixed local and remote calls, pass the location of each actual call instead
of hard-coding it. The SDK's `byok_kind` can identify local and remote BYOK
calls; the application must resolve an unknown location rather than guess.
Record each event once, and do not also record the same invocation through the
Ollama adapter. The SDK reports input, output, cache reads and writes, reasoning,
and duration when available. Cache reads and writes are subsets of input;
reasoning is a subset of output. This integration requires access to the
owning application's live SDK session and cannot attach to another process or
recover an event that was not captured.

## Recording other measured usage

When a provider or host exposes invocation usage, record the actual counts:

```sh
telemetry.py record --task-id TASK --provider PROVIDER --model MODEL \
  --location remote --input-tokens 120 --output-tokens 40 \
  --processing-tokens 10 --cached-input-tokens 20
```

Provide at least one of `--input-tokens`, `--output-tokens`, or
`--total-tokens`. When any two are known, the third is calculated.
`--duration-ns` is optional. Cached input is included in input; processing
(such as reasoning tokens) is included in output, not added to the total.
Only supply those breakdowns if the provider reports them using these
semantics. The Ollama processing count described above is derived from visible
thinking text rather than reported as a separate provider usage field.
The CLI rejects inconsistent or negative counts. `measured_fields` distinguishes
supplied counts from derived ones. Recording is explicit; this skill does not
automatically capture usage from calls made outside its adapter.

Reports sum known counts, including historical records whose totals can be
derived. A total can therefore be partial if some invocations lack counts; JSON
breakdown coverage and TCR show how much was measured. `N/A` and JSON `null`
mean the information cannot be obtained from the supplied data; they are not
assumed to be zero. A genuine measured or calculated zero remains zero.
Ollama prompt evaluation, output evaluation, and model load durations are
stored and reported in nanoseconds when provided. Duration totals sum available
measurements, not elapsed wall-clock task time.
Telemetry status `Complete` means input, output, and invocation duration were
available; it does not imply optional processing or cached-input counts exist.

## Baselines

```sh
telemetry.py baseline --task-id TASK --remote-tokens 10000 \
  --task-type "code-change" --model "remote-model" --prompt-version "v1"
```

Baseline values must be measured. Estimated values are not accepted by the default CLI.
