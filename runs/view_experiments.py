#!/usr/bin/env python3
"""Dump `git show` for each experiment commit in results.tsv into a readable file."""
import csv
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent / "SymbolicRegression.jl"
TSV = HERE / "results.tsv"
OUT = HERE / "experiments.diff"

STATUS_MARK = {"keep": "[KEEP]", "discard": "[DISCARD]", "crash": "[CRASH]"}


def git_show(commit: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO), "show", "--stat", "--patch", commit],
            capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        return f"(git show failed: {e.stderr.strip()})\n"


def main() -> int:
    if not TSV.exists():
        print(f"missing {TSV}", file=sys.stderr)
        return 1

    with TSV.open() as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    with OUT.open("w") as f:
        f.write("=" * 100 + "\n")
        f.write(f"  AUTORESEARCH EXPERIMENTS  ({len(rows)} total)\n")
        f.write("=" * 100 + "\n\n")

        f.write(f"{'exp':>4}  {'commit':<10}  {'score':>8}  {'ok/fail':>8}  {'status':<8}  description\n")
        f.write("-" * 100 + "\n")
        for r in rows:
            f.write(
                f"{r['exp']:>4}  {r['commit']:<10}  {r['score']:>8}  "
                f"{r['datasets_ok']+'/'+r['datasets_fail']:>8}  "
                f"{r['status']:<8}  {r['description']}\n"
            )
        f.write("\n")

        for r in rows:
            mark = STATUS_MARK.get(r["status"], f"[{r['status'].upper()}]")
            header = (
                f"exp {r['exp']}  |  {r['commit']}  |  score {r['score']}  "
                f"|  ok {r['datasets_ok']} / fail {r['datasets_fail']}  |  {mark}"
            )
            f.write("\n" + "=" * 100 + "\n")
            f.write(header + "\n")
            f.write(f"description: {r['description']}\n")
            f.write("=" * 100 + "\n\n")
            f.write(git_show(r["commit"]))
            f.write("\n")

    print(f"wrote {OUT}  ({len(rows)} experiments)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
