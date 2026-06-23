#!/usr/bin/env python3
"""Benchmark: how much LESS the LLM writes thanks to the slot-file contract.

WHY THIS EXISTS
---------------
A naive /tailor would have the model emit the whole ``resume.tex`` -- ~180 lines
of LaTeX, every save, with every chance to fabricate a number or break a brace.
Instead the model writes only ``output/<company>/resume.slots.json``: a tiny typed
pick (which projects, which bullets by id, the skill rows). Deterministic Python
(``assemble_resume.assemble``) expands that into the real ``resume.tex`` from the
master pool. This script measures what that contract buys on the OUTPUT side:

    * bytes / lines the model actually emits  (slots)  vs  would emit (full tex)
    * an order-of-magnitude token estimate of the same

The accuracy/honesty win is structural and not scored here: because Python -- not
the model -- writes the LaTeX, the model cannot emit a broken brace or an
untraceable number. This script only quantifies the SIZE reduction.

Run:  .venv/bin/python bench/slot_vs_tex.py   (no pdflatex needed -- assemble only)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / ".claude" / "skills" / "tailor" / "scripts"
SRC = REPO / "src"
for _p in (str(SCRIPTS), str(SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SAMPLE_COMPANY = "Nuro_SWE"
SAMPLE_FIXTURE = REPO / "bench" / "sample.slots.json"  # committed; output/ is gitignored
CHARS_PER_TOKEN = 3.5  # same rough English+LaTeX ratio det_vs_llm.py uses


@dataclass(frozen=True)
class Artifact:
    """Size of one text artifact the model either does or would emit."""
    name: str
    bytes: int
    lines: int
    tokens_est: int


def measure(name: str, text: str) -> Artifact:
    return Artifact(
        name=name,
        bytes=len(text.encode("utf-8")),
        lines=text.count("\n") + 1,
        tokens_est=round(len(text) / CHARS_PER_TOKEN),
    )


def build_report() -> dict[str, object]:
    import assemble_resume  # noqa: E402  (SCRIPTS on path above)
    from paths import OUTPUT  # noqa: E402

    out_dir = OUTPUT / SAMPLE_COMPANY
    out_dir.mkdir(parents=True, exist_ok=True)
    slots_path = out_dir / "resume.slots.json"
    slots_path.write_text(SAMPLE_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    # Deterministic expand: slot pick -> full resume.tex (no model, no pdflatex).
    tex_path = assemble_resume.assemble(SAMPLE_COMPANY, force=True)

    slots = measure("resume.slots.json (model emits)",
                    slots_path.read_text(encoding="utf-8"))
    tex = measure("resume.tex (model would emit)",
                  tex_path.read_text(encoding="utf-8"))

    def ratio(a: int, b: int) -> float:
        return round(b / max(1, a), 1)

    return {
        "sample_company": SAMPLE_COMPANY,
        "chars_per_token_est": CHARS_PER_TOKEN,
        "artifacts": [asdict(slots), asdict(tex)],
        "reduction_x": {
            "bytes": ratio(slots.bytes, tex.bytes),
            "lines": ratio(slots.lines, tex.lines),
            "tokens_est": ratio(slots.tokens_est, tex.tokens_est),
        },
    }


def main() -> int:
    try:
        rep = build_report()
    except Exception as e:  # noqa: BLE001 - surface assemble failures clearly
        print(f"could not build slot/tex sample: {e}\n"
              f"check the .venv + assets/master_resume.tex.", file=sys.stderr)
        return 2
    (REPO / "bench" / "slot_vs_tex.json").write_text(
        json.dumps(rep, indent=2), encoding="utf-8")
    from typing import cast

    arts = cast("list[dict[str, object]]", rep["artifacts"])
    red = cast("dict[str, object]", rep["reduction_x"])
    print(f"sample: {rep['sample_company']}  (slot-file contract vs full LaTeX)")
    print("-" * 72)
    for a in arts:
        print(f"{a['name']:<32} {a['bytes']:>6} B  {a['lines']:>4} lines  "
              f"~{a['tokens_est']:>5} tok")
    print("-" * 72)
    print(f"model emits  {red['bytes']}x fewer bytes / {red['lines']}x fewer lines / "
          f"{red['tokens_est']}x fewer tokens  by writing the slot file, not the tex")
    print("-> bench/slot_vs_tex.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
