#!/usr/bin/env python3
"""CLI for the tailor program. Canonical form: ``python -m tailor``.

Grammar (a tiny custom argv parse -- ``force`` is a positional keyword, not a
flag, per the chosen ergonomics)::

    tailor                       tailor every JD with no output/<stem>/ yet
    tailor --force               re-tailor ALL JDs (ignore skip; for testing)
    tailor why <glob> [<glob>…]  apply-time why-company for matched JDs
    tailor force why <glob>…     regenerate why even if present

Ergonomic launch in WSL (one line in ~/.bashrc)::

    tailor(){ ( cd ~/Breakthrough/Resume && .venv/bin/python -m tailor "$@"; ) }
"""

from __future__ import annotations

import sys

from . import discover_jds, run, why


def main(argv: list[str]) -> int:
    force = False
    if argv and argv[0] == "force":           # positional keyword: `force why …`
        force, argv = True, argv[1:]
    elif "--force" in argv:                    # flag form for the batch verb
        force, argv = True, [a for a in argv if a != "--force"]

    if argv and argv[0] == "why":
        globs = argv[1:]
        if not globs:
            print("usage: tailor [force] why <glob> [<glob>...]", file=sys.stderr)
            return 2
        written = why(globs, force)
        print(f"wrote {len(written)} why_company.md file(s)")
        return 0

    if argv:
        print(f"unrecognized arguments: {' '.join(argv)}", file=sys.stderr)
        print("usage: tailor | tailor --force | tailor [force] why <glob>...", file=sys.stderr)
        return 2

    jds = discover_jds()
    if not jds:
        print("no jobDescription/*.txt found", file=sys.stderr)
        return 1
    reports = run(jds, force)
    failures = sum(1 for r in reports if not r.shippable)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
