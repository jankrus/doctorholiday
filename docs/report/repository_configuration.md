# Repository Configuration & Branch Protection

To meet the requirements of the exam assignment (§7a) and establish a Secure Software Development Life Cycle (SSDLC), administrative safeguards and policies have been implemented in the `jankrus/doctorholiday` repository.

---

## 1. Branch Rulesets (`protect-main`)

The default branch, `main`, serves as the reference for release-ready code. To prevent uncontrolled changes and data loss, the `protect-main` ruleset (Ruleset ID: `25552098`) has been configured with the following rules:

| Rule | Configuration | Rationale / SSDLC Relevance |
| :--- | :--- | :--- |
| **Target Branch** | `~DEFAULT_BRANCH` (`main`) | Protects the production codebase. |
| **Pull Request Requirement** | Required (`required_approving_review_count: 1`) | Enforces the four-eyes principle. No code can enter `main` without peer review. |
| **Review Hygiene** | `dismiss_stale_reviews_on_push: true`<br>`required_review_thread_resolution: true` | New pushes invalidate existing approvals; all review comments must be explicitly resolved before merging. |
| **Block Force Pushes** | Enabled (`type: non_fast_forward`) | Prevents the Git history from being overwritten or destroyed. |
| **Restrict Deletions** | Enabled (`type: deletion`) | Protects against accidental or malicious deletion of the main branch. |
| **Status Checks** | Required (CI pipeline) | Merges are permitted only after tests, linting, and security gates (Gitleaks, container scans) have completed successfully. |

---

## 2. Code Security & Analysis

The following native GitHub security features have been enabled in the repository settings:

* **Secret Scanning & Push Protection:** Prevents API keys, tokens, or private certificates from being accidentally committed before a Git push is completed.
* **Dependabot Alerts & Security Updates:** Automatically monitors third-party libraries (React/Node.js, Python/FastAPI) for known CVEs and suggests security patches.

---

## 3. Lecturer Access (§7a)

Before the submission deadline, the lecturer was invited to the repository as a collaborator with the **Maintain** role, providing access to the code, CI/CD pipelines, test reports, and evidence.

---

## 4. Visibility, CI/CD Implications & Deviations

### A. Repository Visibility & Container Registry (GHCR)

The repository is designated as **Private**. This private visibility has the following technical implications:

* **Image Pull Secrets:** When deploying the containerized application to the local Kubernetes cluster (`kind`), images can no longer be pulled publicly from the GitHub Container Registry (GHCR). An `imagePullSecret` with the appropriate read permissions (a GitHub Personal Access Token) is required in the cluster.
* **Evidence Commits:** Automated commits by CI runners (e.g., `github-actions[bot]` for audit trails and evidence artifacts) require dedicated write permissions or must be stored in separate evidence branches.

### B. Note on GitHub Free Tier (Enforcement Limitation)

For private repositories under personal GitHub user accounts, active enforcement of rulesets requires a GitHub Team or Enterprise plan.

* **Documented deviation:** The ruleset was fully configured via the GitHub API and added to the repository. The team’s internal process policies make compliance with the requirements (PRs, reviews, status checks) mandatory, even though GitHub restricts enforcement on the Free tier to organization accounts.
