#!/usr/bin/env python3
from datetime import timedelta

from telemetry import append_record, normalize_invocation, telemetry_file


def record_usage(data, task_id, location):
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
    record = normalize_invocation(
        fields, task_id, provider=getattr(data, "model_provider", None) or "copilot",
        model=model, location=location, telemetry_source="copilot_sdk_usage")
    append_record(telemetry_file(), record)
    return record
