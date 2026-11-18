#!/usr/bin/env bash
# One-time setup of the cosign key pair for image signing (issue #35). Run it once, on a trusted
# machine, as a person who may write secrets of the repository (`gh auth status`).
#
#   scripts/setup-signing-key.sh [owner/repo]
#
# What it does
#   1. generates a key pair with cosign (the pinned cosign container, or `cosign` if COSIGN is set)
#      in a private directory, with a random password that is never printed;
#   2. creates the environment `signing`, which only the branch `main` may use, and stores the private
#      key and the password in it as the secrets COSIGN_PRIVATE_KEY and COSIGN_PASSWORD (read from
#      files through stdin, never on a command line); the sign job declares `environment: signing`;
#   3. writes the public key to infrastructure/signing/cosign.pub (commit this file, nothing else);
#   4. deletes the private key and the password from this machine.
# Afterwards the private key exists only as a GitHub secret. To rotate it, run the script again,
# commit the new public key and record the date in docs/architecture/signing.md. It refuses to run
# if the public key already exists, so a key is never replaced by accident.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
repo="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
pub="infrastructure/signing/cosign.pub"
# Pinned by digest (AGENTS.md rule 7).
COSIGN_IMAGE="ghcr.io/sigstore/cosign/cosign:v3.1.4@sha256:0f06154836d2de34f887a5c273506d52ca43edaa1d9e53e6510fa78a48f69c2d"

[[ ! -e "$pub" ]] || { echo "$pub exists already; delete it on purpose to rotate the key." >&2; exit 1; }
gh auth status > /dev/null 2>&1 || { echo "gh is not logged in" >&2; exit 1; }

mkdir -p .cache
dir="$(mktemp -d .cache/signing-key.XXXXXX)"
chmod 700 "$dir"
cleanup() {
  # Only the two files this script created, then the empty directory.
  [[ -n "${dir:-}" ]] && rm -f "$dir/cosign.key" "$dir/cosign.pub" "$dir/password" && rmdir "$dir" 2> /dev/null || true
}
trap cleanup EXIT

umask 077
openssl rand -hex 32 > "$dir/password"
if [[ -n "${COSIGN:-}" ]]; then
  (cd "$dir" && COSIGN_PASSWORD="$(cat password)" "$COSIGN" generate-key-pair > /dev/null)
else
  # MSYS_NO_PATHCONV: Git Bash on Windows must not rewrite the container paths.
  MSYS_NO_PATHCONV=1 docker run --rm -e COSIGN_PASSWORD="$(cat "$dir/password")" \
    -v "$(cd "$dir" && (pwd -W 2> /dev/null || pwd)):/keys" -w /keys "$COSIGN_IMAGE" generate-key-pair > /dev/null
fi
[[ -s "$dir/cosign.key" && -s "$dir/cosign.pub" ]] || { echo "key generation failed" >&2; exit 1; }

# Environment limited to the branch main (custom branch policy), so a workflow on another branch
# cannot get the key even if someone edits the workflow.
gh api --method PUT "repos/$repo/environments/signing"   -F 'deployment_branch_policy[protected_branches]=false'   -F 'deployment_branch_policy[custom_branch_policies]=true' > /dev/null
gh api --method POST "repos/$repo/environments/signing/deployment-branch-policies"   -f name=main -f type=branch > /dev/null 2>&1 || true  # already there on a re-run

gh secret set COSIGN_PRIVATE_KEY --repo "$repo" --env signing < "$dir/cosign.key"
gh secret set COSIGN_PASSWORD --repo "$repo" --env signing < "$dir/password"

mkdir -p "$(dirname "$pub")"
cp "$dir/cosign.pub" "$pub"
echo "Environment signing (branch main only) with the secrets COSIGN_PRIVATE_KEY and COSIGN_PASSWORD is set up for $repo."
echo "Public key written to $pub. Commit it:"
echo "  git add $pub && git commit -m 'chore(signing): add the cosign public key'"
