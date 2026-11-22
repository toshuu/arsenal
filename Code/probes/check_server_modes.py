"""Check the call-stream mode helpers without a GPU."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from batch.server import (  # noqa: E402
    CALL_STREAM_SETTINGS,
    quality_stream_raw,
    resolve_call_stream_mode,
)


def main() -> int:
    result: dict[str, object] = {}
    result["default"] = resolve_call_stream_mode() == "sentence"
    result["utterance"] = resolve_call_stream_mode("utterance") == "utterance"
    result["latency"] = resolve_call_stream_mode("LATENCY") == "latency"
    try:
        resolve_call_stream_mode("bad")
        result["unknown_rejected"] = False
    except ValueError:
        result["unknown_rejected"] = True
    result["sentence_raw"] = quality_stream_raw("sentence") is True
    result["utterance_raw"] = quality_stream_raw("utterance") is True
    result["latency_raw"] = quality_stream_raw("latency") is False
    result["settings"] = (
        CALL_STREAM_SETTINGS["sentence"]["max_first_tokens"] is None
        and CALL_STREAM_SETTINGS["sentence"]["max_allowed_frames"] == 224
        and CALL_STREAM_SETTINGS["utterance"]["max_allowed_frames"] == 512
        and CALL_STREAM_SETTINGS["latency"]["max_first_tokens"] == 16
    )
    result["ok"] = all(v is True for k, v in result.items() if k != "ok")
    print(json.dumps({"ok": bool(result["ok"])}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
