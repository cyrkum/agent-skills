# Ollama integration

`scripts/ollama_adapter.py` calls the official loopback-only `/api/generate` or `/api/chat` endpoint with `stream=false` or streaming enabled. Ollama responses can provide:

- `prompt_eval_count`
- `eval_count`
- `prompt_eval_duration`
- `eval_duration`
- `load_duration`
- `total_duration`
- model identifier

Durations from Ollama are nanoseconds. `total_tokens` is `prompt_eval_count + eval_count`. Prompt and output content are not persisted.
