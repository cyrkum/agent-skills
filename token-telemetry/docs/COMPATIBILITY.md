# Compatibility matrix

| Mechanism | Status | Measurements | Limitation |
|---|---|---|---|
| Ollama native `/api/generate` | Implemented and tested with synthetic metadata | Prompt, output, durations, model | Live model validation required |
| Ollama native `/api/chat` | Implemented | Prompt, output, durations, model | Streaming parser merges final events |
| Instruction fallback | Implemented | Invocation metadata where adapter is invoked | No lifecycle guarantee |
| Agent session logs | Inspected | Existing host session events; no reliable remote counts | Not auto-imported |
| Remote native API | Unsupported by host prerequisites | None confirmed | Requires host API metadata |
| Lifecycle hooks | Unsupported | None | No supported hooks available |
| OpenTelemetry | Unsupported | None | Requires configured exporter |
| Baselines | Implemented | Manual measured baseline | No fabricated values |
