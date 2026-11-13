#!/usr/bin/env python3
"""Count findings in the scan reports of scripts/scan.sh (issues #32, #33).

    report_stats.py sbom <file>          validates a CycloneDX SBOM, prints the number of components
    report_stats.py semgrep <file>       prints the number of Semgrep results (every severity)
    report_stats.py semgrep-error <file> prints the number of Semgrep results of severity ERROR
    report_stats.py trivy <file>         prints the number of HIGH or CRITICAL vulnerabilities
    report_stats.py trivy-all <file>     prints the number of vulnerabilities of every severity
    report_stats.py gitleaks <file>      prints the number of leaks

A report that is missing, empty or not the expected JSON ends with exit code 1 and a message on
stderr: a scan that produced nothing must never look like a clean scan. Standard library only.
"""

import json
import sys
from pathlib import Path

GATE_SEVERITIES = {"HIGH", "CRITICAL"}


def fail(message: str) -> None:
    print(f"report_stats: {message}", file=sys.stderr)
    sys.exit(1)


def load(path: str) -> object:
    file = Path(path)
    if not file.is_file() or file.stat().st_size == 0:
        fail(f"{path} is missing or empty")
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON ({exc.msg})")
    raise AssertionError  # unreachable


def count_sbom(path: str) -> int:
    data = load(path)
    if not isinstance(data, dict) or data.get("bomFormat") != "CycloneDX":
        fail(f"{path} is not a CycloneDX document")
    if not data.get("specVersion"):
        fail(f"{path} has no specVersion")
    components = data.get("components") or []
    if not components:
        fail(f"{path} lists no components")
    return len(components)


def semgrep_results(path: str) -> list[dict]:
    data = load(path)
    if not isinstance(data, dict) or "results" not in data:
        fail(f"{path} is not a Semgrep report")
    return data["results"]


def count_semgrep_errors(path: str) -> int:
    # Semgrep has no CVSS score. For the quality gate (#36) its severity ERROR counts as HIGH or
    # CRITICAL; WARNING and INFO findings (and the MEDIUM hygiene hints) are reported only.
    return sum(1 for r in semgrep_results(path) if r.get("extra", {}).get("severity") == "ERROR")


def trivy_vulnerabilities(path: str) -> list[dict]:
    data = load(path)
    if not isinstance(data, dict) or "Results" not in data and "ArtifactName" not in data:
        fail(f"{path} is not a Trivy report")
    return [
        vulnerability
        for result in data.get("Results") or []
        for vulnerability in result.get("Vulnerabilities") or []
    ]


def count_gitleaks(path: str) -> int:
    data = load(path)
    if not isinstance(data, list):
        fail(f"{path} is not a Gitleaks report")
    return len(data)


def main(argv: list[str]) -> None:
    if len(argv) != 3:
        fail(__doc__.strip().splitlines()[0] + " (usage: report_stats.py <kind> <file>)")
    kind, path = argv[1], argv[2]
    if kind == "sbom":
        print(count_sbom(path))
    elif kind == "semgrep":
        print(len(semgrep_results(path)))
    elif kind == "semgrep-error":
        print(count_semgrep_errors(path))
    elif kind == "trivy":
        print(sum(1 for v in trivy_vulnerabilities(path) if v.get("Severity") in GATE_SEVERITIES))
    elif kind == "trivy-all":
        print(len(trivy_vulnerabilities(path)))
    elif kind == "gitleaks":
        print(count_gitleaks(path))
    else:
        fail(f"unknown kind '{kind}'")


if __name__ == "__main__":
    main(sys.argv)
