#!/usr/bin/env python3
"""Quality gate of the pipeline (brief §3e, issue #36).

    quality_gate.py [--reports DIR] [--needs FILE] [--verify-cmd CMD]

Reads the reports of the scans and checks the signatures. It fails (exit code 1) on any of

  1. a secret found by Gitleaks,
  2. a vulnerability with severity HIGH or CRITICAL or a CVSS score >= 7.0 in a Trivy report of a
     lockfile (reports/sca/trivy-fs-*.json) or of a built image (reports/gate/trivy-image-*.json),
     and a Semgrep finding of severity ERROR (Semgrep has no CVSS score; ERROR stands for HIGH or
     CRITICAL, the mapping is documented in docs/architecture/quality-gate.md),
  3. an image whose signature or SBOM attestation does not verify against the public key
     (scripts/verify-image.sh) or that has no reference by digest.

The gate fails closed: a report that is missing, empty or not valid is a violation, and so is a
job that did not succeed (--needs: the JSON of `toJSON(needs)`, optional). All rules are checked
even after the first violation, so the report is complete.

Output: reports/gate/quality-gate.json (every rule with its findings), a Markdown summary on stdout
(appended to $GITHUB_STEP_SUMMARY by the workflow). Standard library only.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

COMPONENTS = ("frontend", "backend")
BLOCKING_SEVERITIES = {"HIGH", "CRITICAL"}
CVSS_LIMIT = 7.0
REQUIRED_JOBS = ("sast", "sca", "secrets", "build", "sign")


class ReportError(Exception):
    """A report that must exist is missing, empty or not the expected JSON."""


def load(path: Path):
    if not path.is_file() or path.stat().st_size == 0:
        raise ReportError(f"{path} is missing or empty")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportError(f"{path} is not valid JSON ({exc.msg})") from exc


def max_cvss(vulnerability: dict) -> float:
    """Highest CVSS v3 (or v2 if there is no v3) score over all sources of one vulnerability."""
    scores = []
    for source in (vulnerability.get("CVSS") or {}).values():
        for key in ("V3Score", "V2Score"):
            value = source.get(key)
            if isinstance(value, (int, float)):
                scores.append(float(value))
                break
    return max(scores, default=0.0)


def trivy_findings(path: Path) -> list[dict]:
    data = load(path)
    if not isinstance(data, dict) or ("Results" not in data and "ArtifactName" not in data):
        raise ReportError(f"{path} is not a Trivy report")
    findings = []
    for result in data.get("Results") or []:
        for vulnerability in result.get("Vulnerabilities") or []:
            severity = vulnerability.get("Severity")
            score = max_cvss(vulnerability)
            if severity in BLOCKING_SEVERITIES or score >= CVSS_LIMIT:
                findings.append(
                    {
                        "id": vulnerability.get("VulnerabilityID"),
                        "package": vulnerability.get("PkgName"),
                        "installed": vulnerability.get("InstalledVersion"),
                        "fixed": vulnerability.get("FixedVersion"),
                        "severity": severity,
                        "cvss": score,
                        "target": result.get("Target"),
                    }
                )
    return findings


def semgrep_findings(path: Path) -> list[dict]:
    data = load(path)
    if not isinstance(data, dict) or "results" not in data:
        raise ReportError(f"{path} is not a Semgrep report")
    return [
        {
            "id": r.get("check_id"),
            "file": r.get("path"),
            "line": (r.get("start") or {}).get("line"),
            "severity": "ERROR",
        }
        for r in data["results"]
        if (r.get("extra") or {}).get("severity") == "ERROR"
    ]


def gitleaks_findings(path: Path) -> list[dict]:
    data = load(path)
    if not isinstance(data, list):
        raise ReportError(f"{path} is not a Gitleaks report")
    # The reports are redacted; only where a secret was found is kept.
    return [
        {"rule": leak.get("RuleID"), "file": leak.get("File"), "line": leak.get("StartLine"),
         "commit": (leak.get("Commit") or "")[:12]}
        for leak in data
    ]


def rule(name: str, description: str) -> dict:
    return {"rule": name, "description": description, "passed": True, "violations": []}


def violate(result: dict, message: str, detail=None) -> None:
    result["passed"] = False
    result["violations"].append({"message": message, **({"detail": detail} if detail else {})})


def check_jobs(reports: Path, needs_file: str | None) -> dict:
    result = rule("jobs", "every job the gate depends on succeeded")
    if not needs_file:
        return result
    try:
        needs = json.loads(Path(needs_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        violate(result, f"cannot read the job results ({exc})")
        return result
    for job in REQUIRED_JOBS:
        state = (needs.get(job) or {}).get("result")
        if state != "success":
            violate(result, f"job '{job}' did not succeed (result: {state})")
    return result


def check_secrets(reports: Path) -> dict:
    result = rule("secrets", "Gitleaks found no secret in the history")
    try:
        for finding in gitleaks_findings(reports / "secrets" / "gitleaks.json"):
            violate(result, "secret found", finding)
    except ReportError as exc:
        violate(result, str(exc))
    return result


def check_vulnerabilities(reports: Path) -> dict:
    result = rule("vulnerabilities", f"no HIGH/CRITICAL or CVSS >= {CVSS_LIMIT} finding")
    for component in COMPONENTS:
        reports_to_check = [
            ("trivy-fs", reports / "sca" / f"trivy-fs-{component}.json", trivy_findings),
            ("trivy-image", reports / "gate" / f"trivy-image-{component}.json", trivy_findings),
            ("semgrep", reports / "sast" / f"semgrep-{component}.json", semgrep_findings),
        ]
        for tool, path, reader in reports_to_check:
            try:
                for finding in reader(path):
                    violate(result, f"{tool} {component}: blocking finding", finding)
            except ReportError as exc:
                violate(result, str(exc))
    return result


def check_signatures(reports: Path, verify_cmd: list[str]) -> dict:
    result = rule("signatures", "every image has a valid signature and SBOM attestation")
    for component in COMPONENTS:
        reference_file = reports / "images" / component / "image-ref.txt"
        if not reference_file.is_file() or not reference_file.read_text(encoding="utf-8").strip():
            violate(result, f"{component}: no image reference ({reference_file})")
            continue
        completed = subprocess.run(  # noqa: S603 - fixed command, component from a constant
            [*verify_cmd, component], capture_output=True, text=True, check=False
        )
        if completed.returncode != 0:
            violate(
                result,
                f"{component}: signature or attestation does not verify",
                (completed.stderr or completed.stdout).strip().splitlines()[-3:],
            )
    return result


def markdown(results: list[dict]) -> str:
    passed = all(r["passed"] for r in results)
    lines = [f"### Quality gate: {'PASSED' if passed else 'BLOCKED'}", "", "| Rule | Result | Violations |", "| --- | --- | --- |"]
    for r in results:
        lines.append(f"| {r['description']} | {'pass' if r['passed'] else '**FAIL**'} | {len(r['violations'])} |")
    for r in results:
        for v in r["violations"][:20]:
            lines.append(f"- `{r['rule']}`: {v['message']}")
        if len(r["violations"]) > 20:
            lines.append(f"- `{r['rule']}`: … and {len(r['violations']) - 20} more (see the JSON report)")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--reports", default=os.environ.get("REPORTS_DIR", "reports"))
    parser.add_argument("--needs", help="JSON of toJSON(needs) of the workflow")
    parser.add_argument("--verify-cmd", default="scripts/verify-image.sh",
                        help="command that verifies one image: <cmd> frontend|backend")
    args = parser.parse_args(argv)

    reports = Path(args.reports)
    results = [
        check_jobs(reports, args.needs),
        check_secrets(reports),
        check_vulnerabilities(reports),
        check_signatures(reports, args.verify_cmd.split()),
    ]
    passed = all(r["passed"] for r in results)
    out = reports / "gate"
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "passed": passed,
        "run": os.environ.get("GITHUB_RUN_ID"),
        "sha": os.environ.get("GITHUB_SHA"),
        "rules": results,
    }
    (out / "quality-gate.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(markdown(results))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
