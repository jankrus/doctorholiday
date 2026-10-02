# Doctor Holiday 🩺🏖️

**Doctor Holiday** ist eine kleine, aber vollständige Webanwendung (bestehend aus Frontend und Backend), die als Terminbuchungssystem für eine Arztpraxis dient. Dieses Repository wurde im Rahmen der Prüfungsleistung „Security by Design“ (STG-TINF24F) entwickelt.

Der Schwerpunkt dieses Projekts liegt nicht primär auf der reinen Funktionalität, sondern auf **Security by Design** und einer vollständig nachvollziehbaren, reproduzierbaren Lieferkette (Supply Chain). Vom ersten Commit bis zum Deployment auf einem lokalen Kubernetes-Cluster sind verschiedene Sicherheitsmechanismen tief in den Entwicklungsprozess integriert.

### 🛡️ Core Security Features & DevSecOps:
* **Threat Modeling:** Umfassende Bedrohungsanalyse mittels Systemmodellierung (DFD), STRIDE und Attack-Trees zur Identifikation und Mitigation potenzieller Schwachstellen.
* **Sichere CI/CD-Pipeline:** Automatisierte Workflows bei Änderungen am Main-Branch. Die Pipeline umfasst die Erstellung von Software Bill of Materials (SBOMs), Static Application Security Testing (SAST), Software Composition Analysis (SCA) und automatisiertes Secret-Scanning.
* **Image Signing & Quality Gates:** Container-Images werden signiert und verifiziert. Strenge Quality Gates verhindern den Build bei kritischen Findings (CVSS $\ge7.0$) oder fehlenden Signaturen.
* **Kubernetes Security:** Umsetzung des Least-Privilege-Prinzips im Cluster durch dedizierte Namespaces, minimale Service Accounts, restriktive Network Policies und gehärtete Security Contexts (z. B. `runAsNonRoot: true`, `readOnlyRootFilesystem: true`).
* **Secure Coding:** Fokus auf saubere Fehlerbehandlung, strenge Eingabevalidierung und eine sichere Authentifizierung ohne hartcodierte Secrets.
