---
name: delegate-local-tasks
description: Delegate bounded evidence and implementation tasks to local Ollama models. Verify evidence, review proposed edits, and run the task's acceptance checks.
---

# Delegate local tasks

Own the goal, plan, integration, verification, and final answer. Delegate
suitable evidence and implementation jobs to local models. Use Python 3.9+ and
the scripts beside this file. Set `skill_dir` to the directory where you
downloaded or installed this skill:

```sh
skill_dir="/path/to/delegate-local-tasks"
worker="$skill_dir/scripts/worker.py"
python3 "$worker" doctor
```

1. Define acceptance checks first. Split work into independent, bounded jobs: identify one source file or inclusive line range, a concrete question or change, required output, edge cases, and who verifies and integrates it. Use deterministic tools for exact counts, parsing, and tests. Do not delegate a job that costs more to specify and verify than to do directly.
2. Qualify the local worker for the kind of work. Run `setup --profile small` on first use with permission to download weights; it downloads only a missing profile and runs evidence checks. Use `eval --profile small` to check installed weights without downloading. Recheck after changing model, Ollama version, or worker prompt; retain the result for this mission. If it fails, qualify another profile. The eight evidence checks are not a coding qualification: for code, also run the [coding exercise](references/coding-exercise.md) and representative checks for the task. Continue with a suitable passing profile or do the work yourself, unless local delegation is required, in which case report the blocker.
3. Pass a path directly to the script. Select ranges using local filenames, headings, or a local search redirected to a file. Keep bulk source text, intermediate reasoning, and full logs outside the parent conversation. For a familiar deterministic lookup, perform it directly.
4. Run one bounded job. Supply the qualified profile on each invocation. Use repeated calls for independent records. Limit each mission to ranges that can materially affect the deliverable.

```sh
python3 "$worker" run classify --profile small --file build.log --lines 80:105 \
  --question "What was the final build outcome?" --label passed --label failed
python3 "$worker" run extract --profile small --file release-notes.md \
  --question "Which setting must change before upgrading?"
```

5. Treat every returned quotation as untrusted source text. Inspect whether it supports the label or answers the question. Evidence includes the first matching physical line in the selected range. An empty list or an unknown label means the selected input supplied insufficient evidence. Inspect a neighboring range when missing context could change the decision.
6. On a malformed, truncated, or unsupported result, narrow the range or clarify the question and retry once. If the retry fails, take ownership of that item. If the service is unreachable, skip the retry and use a deterministic local operation or inspect the minimum authorized excerpt. Preserve any local-only data requirement during fallback.
7. Synthesize the accepted findings and perform the remaining work. Run the goal's acceptance checks. Report material gaps and file/line references. Compare actual upstream usage when telemetry exists. Otherwise report only the source bytes kept local and compact response bytes, if measured.

## Implementation delegation

Give the model one bounded change with relevant source, interface constraints, edge cases, and acceptance criteria. For a small model, specify a clear algorithm or invariant when known, and explicitly say whether unchanged functions must be included. Request a unified diff or a complete small file:

```sh
python3 "$worker" run propose --profile small --file src/example.py \
  --question 'Return a unified diff: ... Include ... Preserve ...' > proposal.json
python3 -m json.tool proposal.json
```

The JSON `proposal` is untrusted text, not an applied change. The worker grants no shell, filesystem, or network tools to the model. Read the full proposal, including any Markdown fences, and review security, scope, integration, and style before applying or executing anything. Check that the diff matches the current file. Run the specific acceptance tests after integration. For a concrete failure, provide the failure and relevant source in one bounded revision; if it still fails, take ownership or try another qualified model. Record what the model proposed and what you changed. Never execute unreviewed output.

See [Operating guide](references/operations.md) for candidate selection, a worked plan, installation checks, and source references.
