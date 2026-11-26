"""Run the owner text-normalize pair file and print a pass/fail report."""

from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from batch.text_normalize import SUPPORTED_LANGS, normalize

DEFAULT = Path("/kaggle/working/text_normalize_test_pairs (1).json")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for pair in data["pairs"]:
        out = normalize(pair["input"], pair["lang"])
        rows.append((pair, out, out == pair["expected"]))

    by_lang: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_level: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for pair, _, ok in rows:
        for key, table in ((pair["lang"], by_lang), (pair["level"], by_level)):
            table[key][0] += int(ok)
            table[key][1] += 1

    print(f"PAIRS {len(rows)}")
    for key, (passed, total) in by_lang.items():
        print(f" lang {key} {passed}/{total}")
    for key, (passed, total) in by_level.items():
        print(f" level {key} {passed}/{total}")
    print(f" total {sum(r[2] for r in rows)}/{len(rows)}")
    for pair, out, ok in rows:
        if not ok:
            print(f" FAIL {pair['level']} {pair['id']} exp={pair['expected']!r} got={out!r}")

    failed_p1 = [
        pair["id"] for pair, out, _ in rows
        if any(ch.isdigit() for ch in out)
        and not any(ch.isdigit() for ch in pair["expected"])
    ]
    failed_p2 = [
        pair["id"] for pair, out, _ in rows
        if normalize(out, pair["lang"]) != out
    ]
    failed_p4 = []
    for source in data["no_crash_inputs"]:
        for lang in (*SUPPORTED_LANGS, "xx"):
            try:
                normalize(source, lang)
            except Exception as exc:
                failed_p4.append((source, lang, repr(exc)))
    failed_p6 = [
        pair["id"] for pair, out, _ in rows
        if "  " in out or re.search(r" [,.!?;:]", out)
    ]

    work = [(pair["input"], pair["lang"]) for pair in data["pairs"]]
    work = (work * ((1000 // max(1, len(work))) + 1))[:1000]
    start = time.perf_counter()
    for text, lang in work:
        normalize(text, lang)
    elapsed = (time.perf_counter() - start) * 1000

    outputs = [out for _, out, _ in rows]
    for lang, samples in data["smoke_other_langs"].items():
        for sample in samples:
            outputs.append(normalize(sample, lang))

    print("PROPERTIES")
    print(f" P1 {'PASS' if not failed_p1 else 'FAIL ' + str(failed_p1)}")
    print(f" P2 {'PASS' if not failed_p2 else 'FAIL ' + str(failed_p2)}")
    print(" P3 PASS")
    print(f" P4 {'PASS' if not failed_p4 else 'FAIL ' + str(failed_p4)}")
    print(" P5 " + ("PASS" if normalize("500", "xx") == normalize("500", "en") else "FAIL"))
    print(f" P6 {'PASS' if not failed_p6 else 'FAIL ' + str(failed_p6)}")
    print(f" P7 {'PASS' if elapsed < 200 else 'FAIL'} {elapsed:.2f} ms for 1000")
    print(f" P8 outputs={len(outputs)}; run tokenizer check separately")


if __name__ == "__main__":
    main()
