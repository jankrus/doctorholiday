#!/usr/bin/env python3
"""Checks the security traceability matrix docs/report/traceability.md (issue #47).

    python3 scripts/check_traceability.py [--root DIR] [--evidence-ref REF]

The matrix links every security requirement (SR) and every selected STRIDE threat to its
implementation, its verification and its evidence. This script keeps it honest:

  1. Every SR of docs/architecture/security-requirements.md has at least one control with the
     status Implemented or Partial that names an implementation and a verification.
  2. Every `path` or `path::symbol` in the implementation and verification cells exists: the file is
     in the repository and, with `::symbol`, contains that text (a function, class or test name).
  3. Every repository-relative Markdown link of the matrix resolves.
  4. Every `evidence/...` path in the evidence cells exists in the working tree or on the evidence
     branch (`--evidence-ref`, default origin/evidence; skipped if that ref is not available).
  5. Every threat of the selected STRIDE categories (column "Sel." = yes in
     docs/threat-model/stride.md) has a row in the threat table, and every control a threat row
     names exists.
  6. Statuses are one of Implemented, Partial, Planned, Accepted.

Exit code 1 and one line per problem if anything fails. Standard library only.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

STATUSES = {"Implemented", "Partial", "Planned", "Accepted"}
PATH_SUFFIXES = (".py", ".sh", ".yml", ".yaml", ".md", ".sql", ".conf", ".json", ".ts", ".tsx", ".toml", ".txt", ".mk")
MATRIX = "docs/report/traceability.md"
SR_FILE = "docs/architecture/security-requirements.md"
STRIDE_FILE = "docs/threat-model/stride.md"


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def table_rows(text: str, first_cell: re.Pattern) -> list[list[str]]:
    return [cells(line) for line in text.splitlines() if line.startswith("|") and first_cell.match(cells(line)[0])]


def references(cell: str) -> list[str]:
    """`path` and `path::symbol` tokens that look like repository files."""
    found = []
    for token in re.findall(r"`([^`]+)`", cell):
        base = token.split("::")[0]
        if "<" in base or "*" in base or " " in base or base.startswith("http"):
            continue
        if "/" in base or base.endswith(PATH_SUFFIXES):
            found.append(token)
    return found


def evidence_exists(root: Path, path: str, ref: str | None) -> bool | None:
    if (root / path).exists():
        return True
    if not ref:
        return None
    probe = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "--quiet", ref], capture_output=True, text=True)
    if probe.returncode != 0:
        return None
    listing = subprocess.run(["git", "-C", str(root), "ls-tree", "--name-only", ref, "--", path], capture_output=True, text=True)
    return bool(listing.stdout.strip())


def check(root: Path, evidence_ref: str | None) -> list[str]:
    problems: list[str] = []
    matrix = (root / MATRIX).read_text(encoding="utf-8")
    controls = table_rows(matrix, re.compile(r"^C-\d\d\.\d+$"))
    threats = table_rows(matrix, re.compile(r"^TH-\d+$"))
    if not controls:
        problems.append("no control rows (first cell C-xx.n) found")
    control_ids = {row[0] for row in controls}

    # 6. statuses and shape
    for row in controls:
        if len(row) != 7:
            problems.append(f"{row[0]}: expected 7 columns, found {len(row)}")
            continue
        _, sr, _, impl, verif, evidence, status = row
        if status not in STATUSES:
            problems.append(f"{row[0]}: unknown status '{status}'")
        if status in {"Implemented", "Partial"} and (impl in {"", "-", "–"} or verif in {"", "-", "–"}):
            problems.append(f"{row[0]}: status {status} needs an implementation and a verification")
        # 2. file references
        for cell in (impl, verif):
            for token in references(cell):
                path, _, symbol = token.partition("::")
                file = root / path
                if not file.is_file():
                    problems.append(f"{row[0]}: file not found: {path}")
                elif symbol and symbol not in file.read_text(encoding="utf-8", errors="replace"):
                    problems.append(f"{row[0]}: '{symbol}' not found in {path}")
        # 4. evidence paths
        for token in re.findall(r"`(evidence/[^`]+)`", evidence):
            if "<" in token or "*" in token:
                continue
            found = evidence_exists(root, token, evidence_ref)
            if found is False:
                problems.append(f"{row[0]}: evidence not found: {token}")
    for row in threats:
        if len(row) != 7:
            problems.append(f"{row[0]}: expected 7 columns, found {len(row)}")
            continue
        status = row[5]
        if status not in STATUSES:
            problems.append(f"{row[0]}: unknown status '{status}'")
        for cid in re.findall(r"C-\d\d\.\d+", row[4]):
            if cid not in control_ids:
                problems.append(f"{row[0]}: unknown control {cid}")
        if status in {"Implemented", "Partial"} and not re.search(r"C-\d\d\.\d+", row[4]):
            problems.append(f"{row[0]}: status {status} names no control")

    # 1. every SR has an implemented or partial control with implementation and verification
    sr_text = (root / SR_FILE).read_text(encoding="utf-8")
    srs = sorted(set(re.findall(r"^\| \[(SR-\d\d)\]", sr_text, re.M)))
    for sr in srs:
        rows = [r for r in controls if len(r) == 7 and r[1] == sr and r[6] in {"Implemented", "Partial"}]
        if not rows:
            problems.append(f"{sr}: no control with status Implemented or Partial")

    # 5. every selected threat has a row
    stride = (root / STRIDE_FILE).read_text(encoding="utf-8")
    selected = [r[0] for r in table_rows(stride, re.compile(r"^TH-\d+$")) if len(r) > 3 and r[3].lower() == "yes"]
    have = {r[0] for r in threats}
    for th in selected:
        if th not in have:
            problems.append(f"{th}: selected threat (Sel. = yes) has no row in the threat table")
    for th in sorted(have - {r[0] for r in table_rows(stride, re.compile(r"^TH-\d+$"))}):
        problems.append(f"{th}: not a threat of stride.md")

    # 3. links
    for target in re.findall(r"\]\(([^)]+)\)", matrix):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path = target.split("#")[0]
        if path and not (root / MATRIX).parent.joinpath(path).resolve().exists():
            problems.append(f"link does not resolve: {target}")
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence-ref", default="origin/evidence")
    args = parser.parse_args(argv)
    problems = check(Path(args.root).resolve(), args.evidence_ref)
    for problem in problems:
        print(f"FAIL  {problem}")
    if problems:
        print(f"\n{len(problems)} problem(s) in the traceability matrix.")
        return 1
    print("Traceability matrix OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
