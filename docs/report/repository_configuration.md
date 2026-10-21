# Repository-Konfiguration & Branch Protection

Zur Erfüllung der Vorgaben aus der Prüfungsleistung (§7a) sowie zur Etablierung eines Secure Software Development Life Cycle (SSDLC) wurden administrative Schutzmaßnahmen und Richtlinien im Repository `jankrus/doctorholiday` implementiert.

---

## 1. Branch Rulesets (`protect-main`)

Der Standard-Branch `main` dient als Referenz für release-fähigen Code. Um unkontrollierte Änderungen und Datenverlust zu verhindern, wurde das Ruleset `protect-main` (Ruleset-ID: `25552098`) mit folgenden Regeln konfiguriert:

| Regel | Konfiguration | Begründung / SSDLC-Relevanz |
| :--- | :--- | :--- |
| **Target Branch** | `~DEFAULT_BRANCH` (`main`) | Schutz der produktiven Codebasis. |
| **Pull Request Requirement** | Erforderlich (`required_approving_review_count: 1`) | Durchsetzung des Vier-Augen-Prinzips. Kein Code gelangt ohne Peer Review in `main`. |
| **Review Hygiene** | `dismiss_stale_reviews_on_push: true`<br>`required_review_thread_resolution: true` | Neue Pushes invalidieren bestehende Approvals; alle Review-Kommentare müssen vor dem Merge explizit aufgelöst werden. |
| **Block Force Pushes** | Aktiv (`type: non_fast_forward`) | Verhindert das Überschreiben oder Zerstören der Git-Historie. |
| **Restrict Deletions** | Aktiv (`type: deletion`) | Schutz vor versehentlichem oder böswilligem Löschen des Haupt-Branches. |
| **Status Checks** | Erforderlich (CI-Pipeline) | Merges werden erst nach erfolgreichem Durchlauf von Tests, Linting und Security-Gates (Gitleaks, Container-Scans) freigegeben. |

---

## 2. Code Security & Analysis

In den Repository-Einstellungen wurden folgende native GitHub-Sicherheitsmechanismen aktiviert:

* **Secret Scanning & Push Protection:** Verhindert das versehentliche Committen von API-Keys, Tokens oder privaten Zertifikaten bereits vor dem Abschluss des Git-Push-Vorgangs.
* **Dependabot Alerts & Security Updates:** Automatisiertes Monitoring von Drittanbieter-Bibliotheken (React/Node.js, Python/FastAPI) auf bekannte CVEs mit Vorschlägen für Sicherheitspatches.

---

## 3. Dozentenzugriff (§7a)

Der Dozent wurde vor Ablauf der Abgabefrist mit der Rolle **Maintain** als Collaborator zum Repository eingeladen, um Einsicht in Code, CI/CD-Pipelines, Testberichte und Nachweise (Evidences) zu ermöglichen.

---

## 4. Visibility, CI/CD-Auswirkungen & Deviations

### A. Repository-Sichtbarkeit & Container Registry (GHCR)
Das Repository ist als **Private** deklariert. Aus der privaten Sichtbarkeit ergeben sich folgende technische Implikationen:
* **Image Pull Secrets:** Beim Ausrollen der containerisierten Anwendung im lokalen Kubernetes-Cluster (`kind`) können Images aus der GitHub Container Registry (GHCR) nicht mehr öffentlich bezogen werden. Es ist ein `imagePullSecret` mit entsprechenden Read-Berechtigungen (GitHub Personal Access Token) im Cluster erforderlich.
* **Evidence Commits:** Automatisierte Commits durch CI-Runner (z. B. `github-actions[bot]` für Audit-Trails und Evidence-Artefakte) erfordern dedizierte Schreibrechte oder die Ablage in separaten Evidence-Branches.

### B. Hinweis zu GitHub Free Tier (Enforcement-Einschränkung)
In privaten Repositories auf persönlichen GitHub-Benutzeraccounts erfordert die aktive Durchsetzung (*Enforcement*) von Rulesets einen GitHub Team- oder Enterprise-Plan. 
* **Dokumentierte Abweichung:** Die Ruleset-Konfiguration wurde vollständig per GitHub-API angelegt und im Repository hinterlegt. Die internen Prozessrichtlinien des Teams schreiben die Einhaltung (PRs, Reviews, Status-Checks) als verbindlichen Standard fest, auch wenn GitHub das Enforcing im Free-Tier auf Organization-Accounts beschränkt.