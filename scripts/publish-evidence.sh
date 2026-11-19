#!/usr/bin/env bash
# Add the collected evidence of a run to the `evidence` branch (issue #44).
#
#   GH_TOKEN=... scripts/publish-evidence.sh <owner/repo> <collected-dir> <message>
#
# Why a branch and not main: the ruleset of `main` requires a reviewed pull request and has no
# bypass, which is the point of the ruleset. A bot that may push to main would be a hole in it. The
# `evidence` branch holds only the `evidence/` tree and is created on first use (an orphan branch).
# Before the submission, `make evidence-sync` copies it into the working tree of main for a normal
# pull request (docs/report/deviations.md, D-09).
#
# Every run adds files with names of its own, so concurrent runs only race on the push: it is
# repeated after fetching the other run's commit.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <owner/repo> <collected-dir> <message>" >&2
  exit 2
fi
repo="$1"
collected="$(cd "$2" && pwd)"
message="$3"
branch=evidence
: "${GH_TOKEN:?GH_TOKEN is required}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"

# The token travels in a header of this process, not in the remote URL or in .git/config.
auth="$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '\n')"
echo "::add-mask::$auth"
g() { git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $auth" "$@"; }

git init --quiet .
git remote add origin "${EVIDENCE_REMOTE:-https://github.com/$repo.git}"  # EVIDENCE_REMOTE: tests only
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

for attempt in 1 2 3 4 5; do
  if g fetch --quiet --depth 1 origin "$branch" 2> /dev/null; then
    git checkout --quiet -B "$branch" FETCH_HEAD
  else
    git checkout --quiet --orphan "$branch"
  fi
  mkdir -p evidence
  cp -r "$collected"/. evidence/
  git add evidence
  if git diff --cached --quiet; then
    echo "Nothing new to commit."
    exit 0
  fi
  git commit --quiet -m "$message [skip ci]"
  if g push --quiet origin "$branch"; then
    echo "Published to the $branch branch (attempt $attempt)."
    exit 0
  fi
  echo "Push rejected, fetching again (attempt $attempt)."
  sleep $((attempt * 2))
done
echo "Could not publish the evidence." >&2
exit 1
