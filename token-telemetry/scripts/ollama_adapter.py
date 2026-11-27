#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telemetry import append_record, normalize_invocation, telemetry_file


def ollama_url():
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def post(path, payload):
    request = urllib.request.Request(
        ollama_url() + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def reasoning_token_count(thinking, logprobs, eval_count):
    if not isinstance(thinking, str) or not thinking or not isinstance(logprobs, list):
        return None
    if type(eval_count) is not int or not logprobs or len(logprobs) > eval_count:
        return None
    if any(not isinstance(entry, dict) or not isinstance(entry.get("token"), str)
           or not entry["token"] for entry in logprobs):
        return None
    tokens = [entry["token"] for entry in logprobs]
    text = "".join(tokens)
    boundaries = {0: 0}
    offset = 0
    for index, token in enumerate(tokens, 1):
        offset += len(token)
        boundaries[offset] = index
    matches = []
    start = text.find(thinking)
    while start != -1:
        end = start + len(thinking)
        if start in boundaries and end in boundaries:
            matches.append(boundaries[end] - boundaries[start])
            if len(matches) > 1:
                return None
        start = text.find(thinking, start + 1)
    return matches[0] if len(matches) == 1 else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["generate", "chat"])
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt")
    parser.add_argument("--message")
    parser.add_argument("--parent-invocation")
    parser.add_argument("--retry-count", type=int, default=0)
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--count-reasoning", action="store_true",
                        help="request logprobs to count uniquely aligned thinking tokens")
    args = parser.parse_args()

    try:
        if args.command == "generate":
            payload = {"model": args.model, "prompt": args.prompt or "", "stream": args.stream}
            endpoint = "/api/generate"
        else:
            payload = {
                "model": args.model,
                "messages": [{"role": "user", "content": args.message or ""}],
                "stream": args.stream,
            }
            endpoint = "/api/chat"

        if args.count_reasoning:
            payload["logprobs"] = True
        body = post(endpoint, payload)
        thinking = []
        logprobs = []
        if args.stream:
            final = {}
            for line in body.splitlines():
                if line:
                    event = json.loads(line)
                    if args.count_reasoning:
                        chunk = event.get("thinking") if args.command == "generate" else event.get("message", {}).get("thinking")
                        if chunk:
                            thinking.append(chunk)
                        logprobs.extend(event.get("logprobs") or [])
                    final.update(event)
        else:
            final = json.loads(body)
            if args.count_reasoning:
                thinking.append(final.get("thinking", "") if args.command == "generate" else
                                final.get("message", {}).get("thinking", ""))
                logprobs = final.get("logprobs") or []
        if final.get("done") is not True:
            raise ValueError("Ollama response did not contain a final event")
        record = normalize_invocation(
            final,
            task_id=args.task_id,
            provider="ollama",
            model=args.model,
            location="local",
            parent_invocation_id=args.parent_invocation,
            retry_count=args.retry_count,
            status="success",
            telemetry_source="ollama_native_api",
        )
        if args.count_reasoning:
            reasoning = reasoning_token_count("".join(thinking), logprobs, final.get("eval_count"))
            if reasoning is not None:
                record["processing_tokens"] = reasoning
                record["derived_fields"] = ["processing_tokens"]
            else:
                print("Reasoning token count unavailable: thinking text did not align uniquely "
                      "with returned logprobs.", file=sys.stderr)
        append_record(telemetry_file(), record)
        print(json.dumps(record, sort_keys=True))
    except Exception as exc:
        record = normalize_invocation(
            {},
            task_id=args.task_id,
            provider="ollama",
            model=args.model,
            location="local",
            parent_invocation_id=args.parent_invocation,
            retry_count=args.retry_count,
            status="failure",
            telemetry_source="ollama_native_api",
        )
        record["error"] = type(exc).__name__
        append_record(telemetry_file(), record)
        print(json.dumps(record, sort_keys=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
