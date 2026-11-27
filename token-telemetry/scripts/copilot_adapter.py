#!/usr/bin/env python3
import argparse
import json
import os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from telemetry import append_record, normalize_invocation, read_jsonl, telemetry_file


def normalize_usage(data, task_id, location, source="copilot_sdk_usage"):
    if location not in ("local", "remote"):
        raise ValueError("location must be local or remote")
    model = data.model
    if not isinstance(model, str) or not model:
        raise ValueError("usage event must identify its model")
    fields = {
        "input_tokens": getattr(data, "input_tokens", None),
        "output_tokens": getattr(data, "output_tokens", None),
        "cached_input_tokens": getattr(data, "cache_read_tokens", None),
        "cache_write_tokens": getattr(data, "cache_write_tokens", None),
        "processing_tokens": getattr(data, "reasoning_tokens", None),
    }
    if any(value is not None and (type(value) is not int or value < 0)
           for value in fields.values()):
        raise ValueError("usage counts must be nonnegative integers")
    inputs = fields["input_tokens"]
    outputs = fields["output_tokens"]
    read = fields["cached_input_tokens"]
    written = fields["cache_write_tokens"]
    reasoning = fields["processing_tokens"]
    if inputs is not None and ((read is not None and read > inputs) or
                               (written is not None and written > inputs) or
                               (read is not None and written is not None and read + written > inputs)):
        raise ValueError("cache counts cannot exceed input tokens")
    if outputs is not None and reasoning is not None and reasoning > outputs:
        raise ValueError("reasoning tokens cannot exceed output tokens")
    duration = getattr(data, "duration", None)
    if duration is not None:
        if not isinstance(duration, timedelta) or duration < timedelta(0):
            raise ValueError("duration must be a nonnegative timedelta")
        fields["duration_ns"] = ((duration.days * 86400 + duration.seconds) * 1_000_000 +
                                 duration.microseconds) * 1000
    return normalize_invocation(
        fields, task_id, provider=getattr(data, "model_provider", None) or "copilot",
        model=model, location=location, telemetry_source=source)


def record_usage(data, task_id, location):
    record = normalize_usage(data, task_id, location)
    append_record(telemetry_file(), record)
    return record


def import_session_usage(events_path, task_id, message_id=None):
    events = read_jsonl(Path(events_path))
    messages = [i for i, event in enumerate(events)
                if event.get("type") == "user.message" and
                (message_id is None or event.get("id") == message_id)]
    if not messages:
        raise ValueError("user message not found in session events")
    start = messages[-1]
    end = next((i for i in range(start + 1, len(events))
                if events[i].get("type") == "user.message"), len(events))
    usage_events = [event for event in events[start + 1:end]
                    if event.get("type") == "session.usage_record"]
    if not usage_events:
        raise ValueError("no usage records found for the selected user message")

    existing = {r["invocation_id"]: r for r in read_jsonl(telemetry_file())
                if r.get("record_type") == "invocation" and
                r.get("telemetry_source") == "copilot_session_usage"}
    pending = []
    seen = set()
    for event in usage_events:
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id or event_id in seen:
            raise ValueError("session usage event ID is missing or duplicated")
        seen.add(event_id)
        if event_id in existing:
            if existing[event_id].get("task_id") != task_id:
                raise ValueError("session usage already imported for another task")
            continue
        usage = event.get("data", {}).get("usage")
        if not isinstance(usage, dict):
            raise ValueError("invalid session usage record")
        provider = usage.get("provider")
        if not isinstance(provider, dict) or provider.get("kind") != "copilot" or usage.get("isByok") is not False:
            raise ValueError("cannot determine execution location for session usage")
        duration = usage.get("duration")
        if duration is not None and (type(duration) not in (int, float) or duration < 0):
            raise ValueError("session duration must be nonnegative milliseconds")
        data = SimpleNamespace(
            model=usage.get("model"), model_provider=provider.get("id"),
            input_tokens=usage.get("inputTokens"), output_tokens=usage.get("outputTokens"),
            cache_read_tokens=usage.get("cacheReadTokens"),
            cache_write_tokens=usage.get("cacheWriteTokens"),
            reasoning_tokens=usage.get("reasoningTokens"),
            duration=timedelta(milliseconds=duration) if duration is not None else None,
        )
        record = normalize_usage(data, task_id, "remote", "copilot_session_usage")
        record["invocation_id"] = event_id
        record["timestamp"] = event["timestamp"]
        pending.append(record)
    for record in pending:
        append_record(telemetry_file(), record)
    return len(pending)


def main():
    parser = argparse.ArgumentParser(description="Import Copilot session usage for one user message")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--events", type=Path, help="path to the session events.jsonl")
    parser.add_argument("--user-message-id", help="user message ID; defaults to the latest")
    args = parser.parse_args()
    events = args.events
    if events is None:
        session_id = os.environ.get("COPILOT_AGENT_SESSION_ID")
        if not session_id or Path(session_id).name != session_id or session_id in (".", ".."):
            parser.error("COPILOT_AGENT_SESSION_ID is unavailable or invalid; specify --events")
        events = Path(os.environ.get("COPILOT_HOME", "~/.copilot")).expanduser() / "session-state" / session_id / "events.jsonl"
    try:
        imported = import_session_usage(events, args.task_id, args.user_message_id)
    except (OSError, ValueError, KeyError, TypeError, OverflowError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Copilot usage import failed: {exc}\n")
    print(f"Imported {imported} Copilot usage events.")


if __name__ == "__main__":
    main()
