#!/usr/bin/env python3
import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"


def runtime_dir():
    return Path(os.environ.get("TOKEN_TELEMETRY_DIR", "~/.agents/data/token-telemetry")).expanduser()


def telemetry_file():
    return runtime_dir() / "telemetry.jsonl"


def baselines_file():
    return runtime_dir() / "baselines.jsonl"


def now():
    return datetime.now(timezone.utc).isoformat()


def append_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("timestamp", now())
    record.setdefault("schema_version", SCHEMA_VERSION)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path):
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def token_value(record, field):
    value = record.get(field)
    if value is not None:
        return value
    inputs = record.get("input_tokens")
    outputs = record.get("output_tokens")
    total = record.get("total_tokens")
    if field == "total_tokens" and inputs is not None and outputs is not None:
        return inputs + outputs
    if field == "input_tokens" and total is not None and outputs is not None and total >= outputs:
        return total - outputs
    if field == "output_tokens" and total is not None and inputs is not None and total >= inputs:
        return total - inputs
    return None


def normalize_invocation(raw, task_id, provider="ollama", model=None, location="local",
                        parent_invocation_id=None, retry_count=0, status="success",
                        telemetry_source="native_api"):
    fields = {
        "input_tokens": raw.get("input_tokens", raw.get("prompt_eval_count")),
        "output_tokens": raw.get("output_tokens", raw.get("eval_count")),
        "total_tokens": raw.get("total_tokens"),
        "processing_tokens": raw.get("processing_tokens"),
        "cached_input_tokens": raw.get("cached_input_tokens", raw.get("prompt_eval_cached_count")),
        "cache_write_tokens": raw.get("cache_write_tokens"),
        "duration_ns": raw.get("duration_ns", raw.get("total_duration")),
        "prompt_eval_duration": raw.get("prompt_eval_duration"),
        "eval_duration": raw.get("eval_duration"),
        "load_duration": raw.get("load_duration"),
    }
    measured = [key for key, value in fields.items() if value is not None]
    input_tokens = token_value(fields, "input_tokens")
    output_tokens = token_value(fields, "output_tokens")
    total_tokens = token_value(fields, "total_tokens")
    duration = fields["duration_ns"]
    completeness = "complete" if input_tokens is not None and output_tokens is not None and duration is not None else (
        "partial" if measured else "missing"
    )
    return {
        "record_type": "invocation",
        "task_id": str(task_id),
        "invocation_id": str(uuid.uuid4()),
        "parent_invocation_id": parent_invocation_id,
        "provider": provider,
        "model": model or raw.get("model"),
        "execution_location": location,
        "input_tokens": input_tokens,
        "cached_input_tokens": fields["cached_input_tokens"],
        "cache_write_tokens": fields["cache_write_tokens"],
        "processing_tokens": fields["processing_tokens"],
        "output_tokens": output_tokens,
        "total_generated_tokens": output_tokens,
        "total_tokens": total_tokens,
        "duration_ns": duration,
        "prompt_eval_duration": fields["prompt_eval_duration"],
        "eval_duration": fields["eval_duration"],
        "load_duration": fields["load_duration"],
        "status": status,
        "telemetry_source": telemetry_source,
        "telemetry_completeness": completeness,
        "measured_fields": measured,
        "retry_count": retry_count,
    }


def nonnegative_int(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return number


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--task-id", required=True)
    end = sub.add_parser("finalize")
    end.add_argument("--task-id", required=True)
    end.add_argument("--status", choices=["passed", "failed"], required=True)
    baseline = sub.add_parser("baseline")
    baseline.add_argument("--task-id", required=True)
    baseline.add_argument("--remote-tokens", type=nonnegative_int, required=True)
    baseline.add_argument("--task-type")
    baseline.add_argument("--model")
    baseline.add_argument("--prompt-version")
    record = sub.add_parser("record", help="record measured invocation usage")
    record.add_argument("--task-id", required=True)
    record.add_argument("--provider", required=True)
    record.add_argument("--model", required=True)
    record.add_argument("--location", choices=["local", "remote"], required=True)
    for field in ("input-tokens", "output-tokens", "total-tokens",
                  "cached-input-tokens", "processing-tokens", "duration-ns"):
        record.add_argument("--" + field, type=nonnegative_int)
    args = parser.parse_args()

    if args.command == "record":
        fields = {field: getattr(args, field) for field in (
            "input_tokens", "output_tokens", "total_tokens", "cached_input_tokens",
            "processing_tokens", "duration_ns")}
        if all(fields[field] is None for field in ("input_tokens", "output_tokens", "total_tokens")):
            parser.error("record requires at least one measured input, output, or total token count")
        inputs, outputs, total = (fields[field] for field in ("input_tokens", "output_tokens", "total_tokens"))
        if inputs is not None and outputs is not None and total is not None and inputs + outputs != total:
            parser.error("total tokens must equal input plus output tokens")
        if total is not None and any(value is not None and value > total for value in (inputs, outputs)):
            parser.error("input and output tokens cannot exceed total tokens")
        cached = fields["cached_input_tokens"]
        processing = fields["processing_tokens"]
        if total is not None and ((cached is not None and cached > total) or
                                  (processing is not None and processing > total) or
                                  (cached is not None and processing is not None and cached + processing > total)):
            parser.error("cached input and processing tokens cannot exceed total tokens")
        inputs = token_value(fields, "input_tokens")
        outputs = token_value(fields, "output_tokens")
        if cached is not None and inputs is not None and cached > inputs:
            parser.error("cached input tokens cannot exceed input tokens")
        if processing is not None and outputs is not None and processing > outputs:
            parser.error("processing tokens cannot exceed output tokens")
        append_record(telemetry_file(), normalize_invocation(
            fields, args.task_id, provider=args.provider, model=args.model,
            location=args.location, telemetry_source="manual_measured"))
    elif args.command == "init":
        append_record(telemetry_file(), {
            "record_type": "task_start", "task_id": args.task_id,
            "invocation_id": None, "parent_invocation_id": None,
            "provider": "agent", "model": None, "execution_location": "unknown",
            "input_tokens": None, "cached_input_tokens": None, "processing_tokens": None,
            "output_tokens": None, "total_generated_tokens": None, "total_tokens": None,
            "duration_ns": None, "status": "started", "telemetry_source": "lifecycle",
            "telemetry_completeness": "missing", "measured_fields": [], "retry_count": 0,
        })
    elif args.command == "finalize":
        append_record(telemetry_file(), {
            "record_type": "task_end", "task_id": args.task_id,
            "invocation_id": None, "parent_invocation_id": None,
            "provider": "agent", "model": None, "execution_location": "unknown",
            "input_tokens": None, "cached_input_tokens": None, "processing_tokens": None,
            "output_tokens": None, "total_generated_tokens": None, "total_tokens": None,
            "duration_ns": None, "status": args.status, "telemetry_source": "lifecycle",
            "telemetry_completeness": "missing", "measured_fields": [], "retry_count": 0,
        })
    else:
        append_record(baselines_file(), {
            "record_type": "baseline", "task_id": args.task_id,
            "invocation_id": None, "parent_invocation_id": None,
            "provider": "remote", "model": args.model,
            "execution_location": "remote", "input_tokens": None,
            "cached_input_tokens": None, "processing_tokens": None, "output_tokens": None,
            "total_generated_tokens": None, "total_tokens": args.remote_tokens,
            "duration_ns": None, "status": "success", "telemetry_source": "manual_measured",
            "telemetry_completeness": "complete", "measured_fields": ["total_tokens"],
            "retry_count": 0, "task_type": args.task_type, "prompt_version": args.prompt_version,
        })
    print(str(telemetry_file() if args.command != "baseline" else baselines_file()))


if __name__ == "__main__":
    main()
