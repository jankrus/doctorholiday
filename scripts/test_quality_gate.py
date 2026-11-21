#!/usr/bin/env python3
"""Tests of scripts/quality_gate.py (issue #36): each failure mode of the gate and the clean case.

    python scripts/test_quality_gate.py

Runs on fixture reports in a temporary directory; the signature check uses a stand-in for
scripts/verify-image.sh (the real one is tested against a registry in #35). Standard library only.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import quality_gate as gate  # noqa: E402

DIGEST = "ghcr.io/jankrus/doctorholiday-%s@sha256:" + "a" * 64


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def trivy(vulnerabilities=()):
    return {"ArtifactName": "x", "Results": [{"Target": "lock", "Vulnerabilities": list(vulnerabilities)}]}


def vulnerability(severity="LOW", cvss=None):
    entry = {"VulnerabilityID": "CVE-2026-0001", "PkgName": "pkg", "Severity": severity}
    if cvss is not None:
        entry["CVSS"] = {"nvd": {"V3Score": cvss}}
    return entry


class GateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.reports = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        write(self.reports / "secrets" / "gitleaks.json", [])
        for component in gate.COMPONENTS:
            write(self.reports / "sca" / f"trivy-fs-{component}.json", trivy())
            write(self.reports / "gate" / f"trivy-image-{component}.json", trivy())
            write(self.reports / "sast" / f"semgrep-{component}.json", {"results": []})
            write(self.reports / "images" / component / "image-ref.txt", DIGEST % component)
        # Stand-in for verify-image.sh: exit code from the file `verify-exit` next to the reports.
        self.verify = self.reports / "verify.py"
        self.verify.write_text(
            "import sys, pathlib\n"
            f"sys.exit(int(pathlib.Path(r'{self.reports}/verify-exit').read_text()))\n",
            encoding="utf-8",
        )
        write(self.reports / "verify-exit", "0")
        self.cmd = [sys.executable, str(self.verify)]

    def run_gate(self, needs=None):
        results = [
            gate.check_jobs(self.reports, needs),
            gate.check_secrets(self.reports),
            gate.check_vulnerabilities(self.reports),
            gate.check_signatures(self.reports, self.cmd),
        ]
        return {r["rule"]: r for r in results}

    def failed(self, results):
        return sorted(name for name, r in results.items() if not r["passed"])

    def test_clean_reports_pass(self):
        self.assertEqual(self.failed(self.run_gate()), [])

    def test_a_secret_blocks(self):
        write(self.reports / "secrets" / "gitleaks.json", [{"RuleID": "generic-api-key", "File": "a.py"}])
        self.assertEqual(self.failed(self.run_gate()), ["secrets"])

    def test_high_severity_blocks(self):
        write(self.reports / "sca" / "trivy-fs-backend.json", trivy([vulnerability("HIGH")]))
        self.assertEqual(self.failed(self.run_gate()), ["vulnerabilities"])

    def test_cvss_seven_blocks_even_if_severity_is_medium(self):
        write(self.reports / "gate" / "trivy-image-frontend.json", trivy([vulnerability("MEDIUM", 7.0)]))
        self.assertEqual(self.failed(self.run_gate()), ["vulnerabilities"])

    def test_cvss_below_seven_and_medium_pass(self):
        write(self.reports / "sca" / "trivy-fs-backend.json", trivy([vulnerability("MEDIUM", 6.9)]))
        self.assertEqual(self.failed(self.run_gate()), [])

    def test_semgrep_error_blocks_but_warning_does_not(self):
        warning = {"check_id": "r", "path": "a", "extra": {"severity": "WARNING"}}
        error = {"check_id": "r", "path": "a", "extra": {"severity": "ERROR"}}
        write(self.reports / "sast" / "semgrep-backend.json", {"results": [warning]})
        self.assertEqual(self.failed(self.run_gate()), [])
        write(self.reports / "sast" / "semgrep-backend.json", {"results": [warning, error]})
        self.assertEqual(self.failed(self.run_gate()), ["vulnerabilities"])

    def test_missing_or_broken_report_blocks(self):
        (self.reports / "secrets" / "gitleaks.json").unlink()
        write(self.reports / "sca" / "trivy-fs-frontend.json", "not json")
        write(self.reports / "gate" / "trivy-image-backend.json", "")
        results = self.run_gate()
        self.assertEqual(self.failed(results), ["secrets", "vulnerabilities"])
        self.assertEqual(len(results["vulnerabilities"]["violations"]), 2)

    def test_failed_verification_blocks(self):
        write(self.reports / "verify-exit", "1")
        results = self.run_gate()
        self.assertEqual(self.failed(results), ["signatures"])
        self.assertEqual(len(results["signatures"]["violations"]), 2)  # both images

    def test_missing_image_reference_blocks(self):
        (self.reports / "images" / "backend" / "image-ref.txt").unlink()
        self.assertEqual(self.failed(self.run_gate()), ["signatures"])

    def test_job_that_did_not_succeed_blocks(self):
        needs = self.reports / "needs.json"
        write(needs, {job: {"result": "success"} for job in gate.REQUIRED_JOBS})
        self.assertEqual(self.failed(self.run_gate(str(needs))), [])
        write(needs, {**{job: {"result": "success"} for job in gate.REQUIRED_JOBS}, "sign": {"result": "failure"}})
        self.assertEqual(self.failed(self.run_gate(str(needs))), ["jobs"])

    def test_main_writes_report_and_exit_code(self):
        needs = ["--reports", str(self.reports), "--verify-cmd", f"{sys.executable} {self.verify}"]
        self.assertEqual(gate.main(needs), 0)
        report = json.loads((self.reports / "gate" / "quality-gate.json").read_text(encoding="utf-8"))
        self.assertTrue(report["passed"])
        write(self.reports / "secrets" / "gitleaks.json", [{"RuleID": "x"}])
        self.assertEqual(gate.main(needs), 1)
        report = json.loads((self.reports / "gate" / "quality-gate.json").read_text(encoding="utf-8"))
        self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
