# Doctor Holiday 🩺🏖️

**Doctor Holiday** ist eine kleine, aber vollständige Webanwendung (bestehend aus Frontend und Backend), die als Terminbuchungssystem für eine Arztpraxis dient. Dieses Repository wurde im Rahmen der Prüfungsleistung „Security by Design“ (STG-TINF24F) entwickelt.

Der Schwerpunkt dieses Projekts liegt nicht primär auf der reinen Funktionalität, sondern auf **Security by Design** und einer vollständig nachvollziehbaren, reproduzierbaren Lieferkette (Supply Chain). Vom ersten Commit bis zum Deployment auf einem lokalen Kubernetes-Cluster sind verschiedene Sicherheitsmechanismen tief in den Entwicklungsprozess integriert.

### 🛡️ Core Security Features & DevSecOps

* **Threat Modeling:** Umfassende Bedrohungsanalyse mittels Systemmodellierung (DFD), STRIDE und Attack-Trees zur Identifikation und Mitigation potenzieller Schwachstellen.
* **Sichere CI/CD-Pipeline:** Automatisierte Workflows bei Änderungen am Main-Branch. Die Pipeline umfasst die Erstellung von Software Bill of Materials (SBOMs), Static Application Security Testing (SAST), Software Composition Analysis (SCA) und automatisiertes Secret-Scanning.
* **Image Signing & Quality Gates:** Container-Images werden signiert und verifiziert. Strenge Quality Gates verhindern den Build bei kritischen Findings (CVSS $\ge7.0$) oder fehlenden Signaturen.
* **Kubernetes Security:** Umsetzung des Least-Privilege-Prinzips im Cluster durch dedizierte Namespaces, minimale Service Accounts, restriktive Network Policies und gehärtete Security Contexts (z. B. `runAsNonRoot: true`, `readOnlyRootFilesystem: true`).
* **Secure Coding:** Fokus auf saubere Fehlerbehandlung, strenge Eingabevalidierung und eine sichere Authentifizierung ohne hartcodierte Secrets.

### 🚀 Inbetriebnahme

1. `make up` erstellt den lokalen kind-Cluster und deployt die Anwendung.
2. **Direkt danach** im Browser ein Konto registrieren und damit anmelden. Der erste erfolgreiche Login auf einem frischen System macht dieses Konto zum `ADMIN` (Prüfungsvorgabe §4, [#15](https://github.com/jankrus/doctorholiday/issues/15)); jede Registrierung legt ein `PATIENT`-Konto an, alle späteren Logins behalten ihre Rolle.

> **Restrisiko:** Wer nach dem Deployment als Erstes einen Login schafft, wird Admin. Ein Zurücksetzen der Datenbank (z. B. `make db-reset`) setzt auch diesen Zustand zurück, danach wird der nächste erste Login wieder Admin. Deshalb ist der eigene Login der Schritt direkt nach `make up`; die Begründung steht in [roles-and-permissions.md](docs/architecture/roles-and-permissions.md#bootstrapping-the-first-admin).

`STAFF`- und `DOCTOR`-Testkonten gibt es, bis Einladungen (FR-02) umgesetzt sind, nur über die lokalen Seed-Daten (`make -C backend seed`, siehe [backend/README.md](backend/README.md#seed-data)). Die Seed-Daten tragen ihren eigenen Admin ein, dann wird kein weiterer Login befördert.

### Project planning Kanban Board

[https://github.com/users/jankrus/projects/1/](https://github.com/users/jankrus/projects/1/)
