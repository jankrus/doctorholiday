#!/usr/bin/env python3
"""Checks the security settings of the pods that are actually running (issue #43, brief §4).

    kubectl get pods --namespace doctorholiday --output json | scripts/check_pod_security.py

Reads the pod list from stdin and checks every container (init containers included) of every pod:

  - not privileged, no privilege escalation, read-only root file system
  - runs as a non-root user (container or pod level)
  - all capabilities dropped, none added
  - seccomp profile RuntimeDefault (container or pod level)
  - no host network, host PID, host IPC or host path volume
  - the service account token is not mounted

Prints PASS/FAIL per check and the image reference each container runs; exit code 1 if anything
fails or if there is no pod at all (an empty list must not look like a pass). Standard library only.
"""

import json
import sys


def check_container(pod: dict, container: dict, kind: str) -> list[tuple[bool, str]]:
    spec = pod["spec"]
    pod_context = spec.get("securityContext") or {}
    context = container.get("securityContext") or {}
    name = f"{pod['metadata']['name']}/{container['name']}"
    caps = context.get("capabilities") or {}
    seccomp = (context.get("seccompProfile") or pod_context.get("seccompProfile") or {}).get("type")
    non_root = context.get("runAsNonRoot", pod_context.get("runAsNonRoot")) is True
    return [
        (context.get("privileged") is not True, f"{name} ({kind}): not privileged"),
        (context.get("allowPrivilegeEscalation") is False, f"{name} ({kind}): no privilege escalation"),
        (context.get("readOnlyRootFilesystem") is True, f"{name} ({kind}): read-only root file system"),
        (non_root, f"{name} ({kind}): runs as non-root"),
        (caps.get("drop") == ["ALL"] and not caps.get("add"), f"{name} ({kind}): capabilities dropped (ALL)"),
        (seccomp == "RuntimeDefault", f"{name} ({kind}): seccomp RuntimeDefault"),
    ]


def check_pod(pod: dict) -> list[tuple[bool, str]]:
    spec = pod["spec"]
    name = pod["metadata"]["name"]
    results = [
        (not spec.get("hostNetwork") and not spec.get("hostPID") and not spec.get("hostIPC"),
         f"{name}: no host network, PID or IPC"),
        (not any("hostPath" in volume for volume in spec.get("volumes") or []), f"{name}: no hostPath volume"),
        (spec.get("automountServiceAccountToken") is False, f"{name}: service account token not mounted"),
    ]
    for container in spec.get("initContainers") or []:
        results += check_container(pod, container, "init")
    for container in spec["containers"]:
        results += check_container(pod, container, "container")
    return results


def main() -> int:
    data = json.load(sys.stdin)
    pods = data.get("items") or []
    if not pods:
        print("FAIL  no pods in the list")
        return 1
    failures = 0
    for pod in pods:
        for passed, text in check_pod(pod):
            print(("PASS  " if passed else "FAIL  ") + text)
            failures += 0 if passed else 1
        for status in (pod.get("status", {}).get("containerStatuses") or []):
            print(f"INFO  {pod['metadata']['name']}/{status['name']} runs {status.get('imageID', status['image'])}")
    print()
    print("Pod security checks passed." if failures == 0 else f"Pod security: {failures} check(s) failed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
