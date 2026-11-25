#!/usr/bin/env bash
# Save the logs of the finished jobs of a workflow run (issue #44, evidence `run/`).
#
#   GH_TOKEN=... scripts/fetch-run-logs.sh <owner/repo> <run-id> <output-dir>
#
# `gh run view --log` refuses to work while the run is still in progress, and the `evidence` job
# is part of the run. The jobs API returns the log of every job that has finished, which is what
# the evidence needs; the log of the evidence job itself is not included (it is not finished).
# Needs the `actions: read` permission. The logs are public to everyone who can see the run, and
# GitHub already masks secrets in them.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <owner/repo> <run-id> <output-dir>" >&2
  exit 2
fi
repo="$1"
run_id="$2"
out="$3"
[[ "$run_id" =~ ^[0-9]+$ ]] || { echo "invalid run id: $run_id" >&2; exit 2; }
mkdir -p "$out"

gh api --paginate "repos/$repo/actions/runs/$run_id/jobs?per_page=100" \
  --jq '.jobs[] | select(.status == "completed") | [.id, .name, .conclusion] | @tsv' |
  while IFS=$'\t' read -r job_id job_name conclusion; do
    # "build (backend)" -> "build-backend"
    slug="$(printf '%s' "$job_name" | tr -c 'A-Za-z0-9' '-' | sed -e 's/--*/-/g' -e 's/^-//' -e 's/-$//')"
    file="$out/job-$slug-$conclusion.log"
    # --allow-escape-sequences: the logs contain ANSI colours and gh refuses them otherwise; the
    # colours are stripped again below. The reason of a failure is shown, never swallowed.
    if gh api --allow-escape-sequences "repos/$repo/actions/jobs/$job_id/logs" > "$file.raw" 2> "$file.err"; then
      sed "s/$(printf '\033')\[[0-9;]*m//g" "$file.raw" > "$file"
      echo "saved $file"
    else
      rm -f "$file"
      echo "no log for job $job_name ($job_id): $(head -c 300 "$file.err")"
    fi
    rm -f "$file.raw" "$file.err"
  done
