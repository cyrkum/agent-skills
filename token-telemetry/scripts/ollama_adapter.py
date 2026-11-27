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

        body = post(endpoint, payload)
        if args.stream:
            final = {}
            for line in body.splitlines():
                if line:
                    event = json.loads(line)
                    final.update(event)
        else:
            final = json.loads(body)
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
