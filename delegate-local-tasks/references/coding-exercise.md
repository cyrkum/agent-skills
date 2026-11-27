# Coding qualification exercise

The evidence `eval` does not test programming. This small, repeatable exercise
is a smoke test, not a guarantee of coding ability. Before a consequential job,
also try representative tasks and acceptance tests in that job's language and
framework. Record model digest, runtime, prompt, cold/warm timing, results, and
whether a revision was needed. Run models one at a time.

Create a scratch `retry_source.py`:

```python
def delay_for_attempt(attempt):
    return min(2 ** attempt, 60)


def retry_after_seconds(value, cap=120):
    raise NotImplementedError
```

Ask the model for a complete file:

```sh
python3 "$worker" run propose --profile small --file retry_source.py \
  --question 'Return the complete Python file. Implement retry_after_seconds(value, cap=120): value is None or a string; return None if absent or invalid; accept only ASCII digits with optional surrounding whitespace; clamp the number to cap; arbitrarily long digit strings must work. Preserve delay_for_attempt; no imports.' > proposal.json
python3 -m json.tool proposal.json
```

Inspect the entire proposal for unsafe behavior, unexpected imports, and changes
outside scope. In a scratch directory, manually save the reviewed Python code
as `candidate.py` (remove Markdown fences if present). Never execute unreviewed
model output. With `skill_dir` set to the downloaded skill directory as in
`SKILL.md`, run:

```sh
python3 "$skill_dir/tests/check_coding_exercise.py" candidate.py
```

The check executes the candidate and exercises absent, malformed, Unicode,
huge, and leading-zero inputs, caps, and the unchanged function. A pass requires
all checks and human review. Failures are useful feedback for one bounded
revision; do not score a revised answer as a first-attempt pass. Do not execute
an unreviewed revision. If it still fails, choose another candidate or have the
orchestrator implement the change. Never treat a single exercise as sufficient
qualification for all code tasks.

For comparison, a more constrained request is:

```text
Output a complete Python module with BOTH functions, including unchanged
delay_for_attempt. No imports. Implement retry_after_seconds(value, cap=120):
value is None or a string; return None if absent, empty, or invalid. Strip
whitespace. Accept only ASCII digits. Parse left to right, updating result to
min(cap, result*10 + digit) on each digit, never converting the whole string.
Examples: ("9"*5000) returns 120, ("0"*5000+"1") returns 1, "１２" returns
None, " 17 " returns 17.
```

This supplies the core algorithm, so a pass measures faithful implementation
of an explicit invariant, not independent problem-solving. Test it separately
and report it separately from the original prompt's result. Stronger guidance
may help for tightly specified jobs, but can cost more to formulate than doing
the change directly.
