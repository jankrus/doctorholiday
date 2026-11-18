# Image signing

Brief §3d and §3e-iii, requirement SR-07, issue #35. Every image that the pipeline pushes to GHCR is signed by its digest with [cosign](https://docs.sigstore.dev/cosign/), and its SBOM is attached as a signed attestation. The quality gate (#36) and the deployment (#43) verify both before an image is used.

## Design

| Decision | Choice | Why |
| :--- | :--- | :--- |
| Key model | key-based (a key pair we hold), not keyless | The submission needs the public keys and a signature bundle per image (§7b-i-5/6); keyless signatures depend on an identity provider and a public log. |
| What is signed | the image **digest** (`image@sha256:...`), never a tag | A tag can be moved after signing; the scripts refuse a reference without a digest. |
| SBOM | CycloneDX attestation (`--type cyclonedx`) of the SBOM that the `sbom` job made | The SBOM is then bound to the exact image and verifiable with the same key. |
| Transparency log | none (deviation D-10) | See [deviations.md](../report/deviations.md). |
| cosign | v3.1.4 (the installer action is pinned by commit SHA, the version is set in the workflow) | Fixed version, so signatures and verification behave the same in CI and on a laptop. |

## Keys

- **Private key and password:** only as secrets of the GitHub environment `signing`, which only the branch `main` may use (a workflow on any other branch cannot read them, even if its file is edited): `COSIGN_PRIVATE_KEY` and `COSIGN_PASSWORD`. In the workflow they are passed as environment variables to the single step that signs (`scripts/sign-image.sh`), never on a command line, in a file or in an artifact; GitHub masks them in the log. Pull requests and forks never run the signing job (`context` output `release`).
- **Public key:** [`infrastructure/signing/cosign.pub`](../../infrastructure/signing/cosign.pub), committed. Its SHA-256 fingerprint is part of every verification report.
- **Created by** `scripts/setup-signing-key.sh` (once): it generates the pair with a random password, creates the environment and stores both secrets in it, writes the public key and deletes the private key from the machine. The script refuses to run while the public key exists.
- **Rotation:** delete `cosign.pub`, run the script again, commit the new key and note the date here. Images signed with the old key stay verifiable only with the old key (keep it in the git history). Rotation dates: none yet.
- **If the private key leaks:** rotate immediately, then re-sign the images that are still in use.

## Pipeline

`sign (<image>)` runs after `build` for each image: download digest and SBOM, `cosign login ghcr.io` with the job token, `scripts/sign-image.sh` (sign and attest), `scripts/verify-image.sh` (verify with the public key, no secret in that step), upload `signing-<image>`. Reports per image:

| File | Content |
| :--- | :--- |
| `signature-<image>.bundle`, `attestation-<image>.bundle` | Sigstore bundles of the signature and of the SBOM attestation |
| `verify-<image>.json`, `verify-attestation-<image>.json` | output of `cosign verify` and `cosign verify-attestation` |
| `tree-<image>.txt` | `cosign tree`: the signature and the SBOM attestation next to the image |
| `public-key-fingerprint-<image>.txt` | fingerprint of the key used |

The `evidence` job (#44) sorts them into `evidence/<image>/signing/`.

## Verify by hand

With [cosign](https://docs.sigstore.dev/cosign/system_config/installation/) installed, for the digest in `evidence/<image>/run/…-image-ref.txt` (or the package page on GHCR):

```sh
cosign verify --key infrastructure/signing/cosign.pub --insecure-ignore-tlog=true \
  ghcr.io/jankrus/doctorholiday-backend@sha256:<digest>
cosign verify-attestation --key infrastructure/signing/cosign.pub --type cyclonedx --insecure-ignore-tlog=true \
  ghcr.io/jankrus/doctorholiday-backend@sha256:<digest>
cosign tree ghcr.io/jankrus/doctorholiday-backend@sha256:<digest>
```

or `scripts/verify-image.sh backend` after `reports/images/backend/image-ref.txt` exists. An unsigned image, an image signed with another key and a reference without digest all make the script exit with 1 (tested against a local registry for #35).

## Not covered

- Signature check at cluster admission (Kyverno / policy-controller): stretch goal #45 (D-05); until then the pipeline gate and the deploy job verify.
- The signature proves that the key holder signed this digest, not that the build was reproducible (see the note on `apk upgrade`, D-04).
