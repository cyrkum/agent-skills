# Compatibility matrix

| Mechanism | Status | Measurements | Limitation |
|---|---|---|---|
| Ollama native `/api/generate` and `/api/chat` | Implemented and live-tested | Prompt, output, cached input, durations, model; optional visible thinking tokens from logprobs | Reasoning count requires exact unique alignment; logprobs are optional and model-dependent |
| Instruction fallback | Implemented | Invocation metadata where adapter is invoked | No lifecycle guarantee |
| Copilot session logs | Explicit task-scoped import | Non-BYOK Copilot input, output, cache, reasoning and duration when reported | Requires persisted `session.usage_record` events; final response usage arrives after the report |
| Copilot SDK | Live `assistant.usage` event adapter | Input, output, cache reads/writes, reasoning, duration when reported | Requires subscription by the owning SDK application; events are ephemeral |
| Other provider usage | Manual measured recording | Input, output, total, cached input, processing, duration | Requires provider or host usage metadata; not automatically captured |
| Lifecycle hooks | Unsupported | None | No supported hooks available |
| OpenTelemetry | Unsupported | None | Requires configured exporter |
| Baselines | Implemented | Manual measured baseline | No fabricated values |
