"""Check that the voice cut comes before end_on_pause.

Run: python Code/probes/check_voice_cut_order.py
Prints: CHECK_VOICE_CUT_ORDER PASS or FAIL
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "Code" / "batch" / "batched_stream.py"


def main() -> int:
    text = SRC.read_text()
    cut = text.index("if self.voice_seconds is not None:")
    pause = text.index("audio = end_on_pause(audio, self.model.config.mimi.sample_rate)")
    ok = cut < pause
    print("CHECK_VOICE_CUT_ORDER PASS" if ok else "CHECK_VOICE_CUT_ORDER FAIL")
    print(f"cut_index={cut} pause_index={pause}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
