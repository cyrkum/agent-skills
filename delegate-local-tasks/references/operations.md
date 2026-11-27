# Operating guide

## Runtime and model selection

On 2026-11-26, the inspected Apple Silicon Mac had 64 GB unified memory, Python 3.14.7, and Ollama 0.40.18. The profiles below passed the eight evidence cases in `worker.py`. Re-evaluate after changing weights, Ollama, or the worker prompt. These checks do not qualify a model for programming.

Use one quantized model at a time. Model suitability is a property of the task and locally measured results. Ollama supports Apple M-series CPU and GPU execution. [Ollama macOS requirements](https://docs.ollama.com/macos)

| Profile | Ollama tag | Registry size | Selection rule |
| --- | --- | ---: | --- |
| small | `qwen3.5:9b-q4_K_M` | 6.6 GB | First qualified candidate for short classifications and literal extractions. |
| standard | `phi4:14b` | 9.1 GB | Independent qualified candidate when the first misses a representative case. |

Registry sizes can change with tag updates. Run identical cases on each candidate and record accuracy, case latency, and model digest when comparing revisions. The first timed inference may include load time. Choose the smallest passing model on representative local records. The eight included cases establish basic behavior. Add known answers from the intended workload before relying on it for consequential decisions. The 2B and 4B Qwen 3.5, Gemma 3 4B, and pre-existing Gemma 4 26B failed at least one case under the earlier worker. [Qwen model variants](https://ollama.com/library/qwen3.5/tags) · [Phi-4 model](https://ollama.com/library/phi4)

For code, run the [coding exercise](coding-exercise.md) as well as examples
representative of the actual task. A model that passes evidence checks may
still generate incorrect code. On Python 3.14, `qwen3.5:9b-q4_K_M`
(`56671c2ab938`) raised `ValueError` for long digit inputs; `phi4:14b`
(`ac896e5b8b34`) accepted Unicode digits and mishandled long inputs. Both
passed evidence checks and remain useful for that role. A newly tested
`qwen2.5-coder:7b` (`dae161e27b0e`) failed an evidence case in the earlier
five-case suite and the same coding exercise and was removed. These results are
specific to the tested prompts and environment, not general model rankings.

The `qwen3-coder:30b` candidate (`06c1097efce0`) failed three of eight evidence
checks and failed the long-input coding cases, including after targeted
feedback; it was removed. The smaller Qwen passed all 14 coding cases and the
unchanged-function check when given the explicit parsing invariant and both
function names in the exercise's constrained prompt. Its initial, less
prescriptive attempt failed. Use it for similarly bounded work with review,
not as evidence it can independently design arbitrary changes.

The default `qwen3.5:27b` tag (`2d2e4b8fc7c0`) resolved to local MLX
safetensors rather than GGUF, so the worker rejected it as designed. A separate
loopback-only trial after checking its local metadata failed three of eight
evidence checks and both long-input coding cases; it was removed. Specify an
explicit GGUF tag when selecting a model: an unsuffixed tag can resolve to a
different format. On these trials, the initial coding request took about 3 s
for 9B, 4.5 s for Phi-4, 2.3 s for the 30B coder, and 13 s for 27B MLX;
load and cache state differed, so these are not controlled speed comparisons.

## Installation and qualification

Use Python 3.9 or later. Skill discovery locations vary by agent; other agents
can explicitly read the downloaded `SKILL.md`. Set `skill_dir` to the directory
where you downloaded or installed this skill before running its commands, so
they work regardless of its location. [Codex skill locations](https://developers.openai.com/codex/skills/)

Open the Ollama application, or start `ollama serve` in a terminal if a service is needed. Run:

```sh
skill_dir="/path/to/delegate-local-tasks"
python3 -B -m unittest discover -s "$skill_dir/tests" -v
python3 "$skill_dir/scripts/worker.py" doctor
python3 "$skill_dir/scripts/worker.py" setup --profile small
```

Only `setup` may download a model. `eval` measures an already installed model. A passing evaluation prints `"passed":true` with each case and wall time. Exit status 0 indicates success, 1 indicates a semantic evaluation failure, and 2 indicates a request, input, or service problem. For recurring semantic failures, select another candidate and repeat qualification:

```sh
python3 "$skill_dir/scripts/worker.py" setup --profile standard
python3 "$skill_dir/scripts/worker.py" eval --profile standard
```

## Worked mission

**Goal.** Determine which release checks require follow-up and write a two-sentence handoff. The inputs are one UTF-8 log per check. A local index or filename list identifies the relevant records.

| Owner | Work | Acceptance |
| --- | --- | --- |
| Orchestrator | Identify the expected checks from the release manifest and select the final attempt in each log. | Every expected check has an input or a documented gap. |
| Local model | Classify each selected attempt as passed or failed, or abstain. | One allowed label and a supporting quotation with a verified source line, or explicit abstention. |
| Orchestrator | Resolve ambiguous outcomes from the minimum relevant lines. Compare results with available exit codes. Write the handoff. | Each claimed failure has evidence. Missing or ambiguous results are identified separately. |

For example, if line 83 reads `Final build failed with exit code 7.`, a valid local result is:

```json
{"label":"failed","evidence":[{"line":83,"quote":"failed with exit code 7"}]}
```

The script accepts up to 5,000 UTF-8 bytes per job. Split longer records at semantic boundaries such as attempts or sections. `--lines A:B` uses 1-based inclusive physical lines. Its end may extend beyond the file. A returned line identifies an occurrence of the quote. The parent must still establish that it refers to the correct attempt or subject. Avoid inferring absence in a whole document from one range. For quantities, dates, or multiple similar identifiers, retain enough surrounding text to disambiguate the claim.

## Context reduction and failure handling

Pass paths before opening source files in the upstream conversation. The client sends the question and selected bytes to the local daemon. It returns at most one quoted line fragment for classification or three for extraction, up to 140 characters each. It checks every quote against the input. A valid schema and literal quotation establish format and provenance. The parent evaluates relevance and meaning. For a deterministic answer already obtainable in a few bytes, use a local parser or search directly.

To measure a run, use shell redirection, e.g. `python3 "$worker" run ... > result.json`, and compare `wc -c` for the selected excerpt and the compact result. Include the command and other parent messages when analyzing upstream billing. Local Ollama token counts, byte differences, and provider-billed upstream tokens measure different things. A brief result can still cost more context than a tiny original record.

The client contacts a fixed loopback address, ignores HTTP proxy settings, rejects redirects and known remote model metadata, and requests known local GGUF model profiles. Workers receive no tools or execution privileges through this interface. Proposal requests accept up to 1,200 UTF-8 bytes and the same 5,000-byte source limit; JSON escaping also counts toward the 7,200-byte prompt budget. A proposal is not applied or executed by the worker. A stopped response is not proof of correctness. Keep the local daemon and model installation under the user's control. If local-only processing is required and Ollama is unavailable, perform deterministic work on the host or report the blocked item.

## Design references

- Use minimal skill metadata and load detailed operating instructions on demand. [Agent Skills specification](https://agentskills.io/specification)
- Keep ownership and final synthesis in the orchestrator. Use explicit acceptance checks before integrating a worker result. [Anthropic workflow patterns](https://www.anthropic.com/engineering/building-effective-agents) · [Orchestrator-workers reference implementation](https://github.com/anthropics/claude-cookbooks/blob/main/patterns/agents/orchestrator_workers.ipynb)
- Use a response schema, low temperature, and explicit output instructions. Check completion status and validate the content locally. [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs) · [Ollama chat API](https://docs.ollama.com/api/chat)
- Community reports describe malformed structured output on particular thinking-model and runtime combinations. The client disables thinking on its Qwen profiles and checks the JSON independently. The cited incident concerned a different MLX model. [Ollama community issue 18441](https://github.com/ollama/ollama/issues/18441)
