# Demo-Skript und Ablaufplan (15 Minuten)

Prüfungsleistung §6: 15 Minuten allein mit dem Prüfer, Überblick und Demonstration der Ergebnisse. Die Folien (elf, mit Titelfolie) stehen in [slides.md](slides.md) (Exporte `slides.pptx` und `slides.pdf`, `make slides`). Die Befehle in diesem Skript wurden gegen den Cluster und die Images aus Pipeline-Lauf 107 ausprobiert; die gemessenen Zeiten stehen dabei.

## 1. Zeitplan

| Zeit | Teil | Inhalt | Sprecher (Vorschlag) |
| :--- | :--- | :--- | :--- |
| 0:00 bis 1:10 | Titel, Ziel, Architektur | Ziel, Ansatz, Architektur | Jan |
| 1:10 bis 2:50 | Threat Modeling, Attack-Tree | Threat Modeling, Attack-Tree | Jan |
| 2:50 bis 4:20 | Sicherheitsfeatures | Sicherheitsfeatures der Anwendung | Noah |
| 4:20 bis 5:50 | Pipeline und Lieferkette | Pipeline, Gate, Signatur | Jan |
| 5:50 bis 6:50 | Kubernetes-Härtung | Kubernetes-Härtung | Felix |
| 6:50 bis 7:30 | Traceability-Matrix | Traceability-Matrix | Felix |
| 7:30 bis 8:10 | Abweichungen, Lessons Learned | Abweichungen, Restrisiken, Lessons Learned | Noah |
| 8:10 bis 14:10 | Demo | **Live-Demo** (Abschnitt 3) | alle drei, siehe unten |
| 14:10 bis 15:00 | – | Puffer, Abschluss, Fragen | – |

Der Sprecherplan ist ein Vorschlag nach der Arbeit im Projekt (Jan: Threat Model, Pipeline, Kubernetes; Noah: Backend und Frontend; Felix: Autorisierung, Secrets, Abhängigkeiten); ändert ihn nach Bedarf, jede Person sollte mindestens zwei Minuten sprechen. **Der Sprecherplan und die Zeiten sind nicht geprobt.** Die Probe mit der Stoppuhr (mindestens zweimal) steht noch aus, siehe Abschnitt 6.

## 2. Vor der Prüfung (Checkliste)

Eine Stunde vorher, auf dem Rechner, der in der Prüfung benutzt wird:

- [ ] Docker läuft, `docker info` antwortet.
- [ ] Werkzeuge vorhanden: `make`, `kind`, `kubectl`, `cosign` (v3.1.4), `openssl`, `curl`, `git`. Unter Windows in Git Bash arbeiten, **nicht** im PowerShell-`bash` (das startet WSL).
- [ ] Aktueller `main`: `git pull`, Arbeitsverzeichnis sauber.
- [ ] Cluster vorgewärmt: `make down` und `make up` einmal ganz durchlaufen lassen (der erste Lauf braucht einige Minuten, das ist der Abschnitt „vorgewärmt“ der Aufgabe). Danach **ein zweites `make up`** zur Probe: es ist wiederholbar und war bei uns nach rund 50 Sekunden bei `Ready`.
- [ ] Das Gate-Demo ist **kein** Live-Teil: Lauf-Link als Browser-Tab geöffnet (siehe Schritt 3).
- [ ] Digest der Images für Schritt 4 liegt bereit: `git fetch origin evidence` und der aktuellste `image-ref.txt` unter `evidence/backend/run/` (oder Digest aus dem letzten grünen Lauf).
- [ ] Browser-Tabs: Repository, Actions-Lauf des Demos, `docs/report/traceability.md`.
- [ ] Terminal mit großer Schrift, ein Fenster, vorbereiteter Verlauf (Befehle aus diesem Skript in der Pfeil-nach-oben-Liste).
- [ ] Ersatz: Bildschirmaufnahmen aller sechs Schritte (Abschnitt 5) auf dem Rechner und auf einem USB-Stick.

**Wichtig:** `make up` ohne Argument baut die Images lokal aus dem Checkout und passt immer zu den Manifesten. `make up IMAGE_SOURCE=registry` nimmt die signierten Images aus GHCR; dann müssen die Digests in `reports/images/<image>/image-ref.txt` aus dem **aktuellsten** Lauf auf `main` stammen, sonst passen Image und Manifeste nicht zusammen (wir hatten das mit einem alten Digest: das Backend verlangte ein entferntes Secret und stürzte ab). In der Demo `make up` ohne Argument verwenden.

## 3. Die Demo (rund 6 Minuten)

Jeder Schritt: Befehl, was dabei gesagt wird, was zu sehen sein muss, und die Rückfallebene.

### Schritt 1: `make up` bis „Ready“ (ca. 1:15)

```sh
make up
```

*Sagen:* „Ein Befehl: Cluster, Calico, Namespace mit Pod Security restricted, Traefik, Secrets zur Laufzeit, Images, Manifeste, Warten bis alles gesund ist.“ Während es läuft, nicht schweigen: auf die Schritte der Ausgabe zeigen.
*Erwartet:* am Ende `https://doctorholiday.localhost answers` und `Ready`.
*Rückfall:* hängt es länger als zwei Minuten, die Aufnahme von Schritt 1 abspielen und weitermachen; der Cluster läuft ja schon (vorgewärmt).

### Schritt 2: die Anwendung und ihre Absicherung (ca. 1:15)

```sh
EXPECT_FIRST_ADMIN=1 make smoke
```

*Sagen:* „Das macht, was ein Browser tut, nur skriptgesteuert: der erste Login wird Admin, ein Cross-Site-Schreibzugriff bekommt 403, ein Patient kann das Audit-Log nicht lesen, nach dem Logout ist die Sitzung weg.“ (`EXPECT_FIRST_ADMIN=1` stimmt nur auf einem frischen System; auf einem Cluster, in dem schon jemand Admin ist, ohne diese Variable laufen lassen.)
*Erwartet:* rund 17 Zeilen `PASS`, am Ende `Smoke test passed.` (etwa 6 Sekunden).
*Rückfall:* Aufnahme; oder im Browser `https://doctorholiday.localhost` öffnen, das Zertifikat akzeptieren und ein Konto registrieren.

### Schritt 3: das Quality Gate blockiert ein Secret (ca. 1:00, aufgezeichneter Lauf)

Im Browser den Lauf öffnen: <https://github.com/jankrus/doctorholiday/actions/runs/45626604342> (Demo `secret`).

*Sagen:* „Wir haben ein Token-förmiges Geheimnis in die Historie einer Wegwerf-Kopie gesetzt und die echten Scans und das echte Gate laufen lassen. Der Lauf ist absichtlich rot. In der Zusammenfassung steht `Quality gate: BLOCKED` und `FAIL` bei Gitleaks; der Schritt ‚Check that the gate decided as expected‘ ist grün: genau diese Regel hat blockiert und keine andere.“ Dann kurz die Läufe für [Schwachstelle](https://github.com/jankrus/doctorholiday/actions/runs/45626611223) und [unsigniertes Image](https://github.com/jankrus/doctorholiday/actions/runs/45626616466) nennen und die grüne Kontrolle [clean](https://github.com/jankrus/doctorholiday/actions/runs/45626597215).
*Erwartet:* Tabelle mit einer Zeile `**FAIL**`.
*Rückfall:* `docs/architecture/quality-gate.md` zeigt die Tabelle der vier Läufe; die Berichte liegen als `demo-secret-…` im Evidence-Branch.

### Schritt 4: Signatur prüfen (ca. 0:50)

```sh
ref=$(cat reports/images/backend/image-ref.txt)
cosign verify --key infrastructure/signing/cosign.pub --insecure-ignore-tlog=true "$ref"
cosign tree "$ref"
```

*Sagen:* „Das Image wird per Digest referenziert, nicht per Tag. Die Signatur prüfen wir mit dem öffentlichen Schlüssel aus dem Repository, ohne Netz-Transparenzlog; das ist in der Doku als Abweichung D-10 begründet. `cosign tree` zeigt die Signatur und das SBOM als Attestation neben dem Image.“
*Erwartet:* `The signatures were verified against the specified public key` (rund 2,5 Sekunden), `tree` zeigt `cyclonedx.org/bom` und `sigstore.dev/cosign/sign/v1`.
*Rückfall:* `evidence/backend/signing/<lauf>-verify-backend.json` und `…-tree-backend.txt` aus dem Evidence-Branch zeigen.
*Voraussetzung:* `reports/images/backend/image-ref.txt` existiert (Checkliste, Digest bereitlegen).

### Schritt 5: NetworkPolicy-Test (ca. 0:50)

```sh
make verify
```

*Sagen:* „Eine Verbindung, die blockiert ist, beweist nur etwas, wenn das Werkzeug funktioniert. Deshalb zeigt der Test Kontrollen, drei Verbindungen, die blockiert sein müssen, und drei, die gehen müssen.“
*Erwartet:* `PASS  throwaway pod -> postgres:5432 is blocked`, `PASS  backend -> example.com:443 is blocked`, `PASS  backend -> postgres:5432 works` (etwa 15 Sekunden).
*Rückfall:* Aufnahme; oder `evidence/backend/run/<lauf>-test-netpol-*.txt`.

### Schritt 6: Security-Context der laufenden Pods (ca. 0:50)

```sh
kubectl --context kind-doctorholiday -n doctorholiday get pod -l app.kubernetes.io/name=backend -o yaml | grep -B1 -A8 'securityContext:'
python3 scripts/check_pod_security.py < <(kubectl --context kind-doctorholiday -n doctorholiday get pods -o json) | tail -3
```

*Sagen:* „Nicht die Manifeste, die laufenden Pods: keine Privilegien-Erhöhung, schreibgeschütztes Dateisystem, alle Capabilities entfernt. Das Skript prüft 36 Punkte an allen Pods und läuft auch in der Pipeline.“
*Erwartet:* `readOnlyRootFilesystem: true`, `capabilities: drop: - ALL`, am Ende `Pod security checks passed.`
*Rückfall:* `evidence/backend/run/<lauf>-pod-security.txt`.

### Zeitreserve

Die sechs Schritte ergeben rund 6 Minuten. Fehlt Zeit, **Schritt 2 und 6 kürzen** (nur die letzten Zeilen zeigen), Schritt 3 und 4 sind die stärksten Belege und bleiben.

## 4. Mögliche Fragen des Prüfers

| Frage | Antwort in einem Satz | Fundstelle |
| :--- | :--- | :--- |
| Warum ist MFA nicht fertig? | Sie ist ein Bonus; wir haben nach dem Attack-Tree zuerst die Lieferkette gebaut. Die Grundlagen (Sitzungszustand, Schlüssel) sind da, der Ablauf fehlt (#21). TOTP wäre ohnehin phishbar, Produktion wäre WebAuthn. | Doku Kapitel d (SR-09), e |
| Warum Alpine mit Shell im Backend-Image? | Für Python 3.12 gibt es kein kostenloses Distroless- oder Chainguard-Image; Pip und Wheel sind entfernt, Nicht-Root, schreibgeschützt. | D-03 |
| Warum kein Transparenzlog (Rekor)? | Schlüsselbasierte Signatur, ein öffentlicher Eintrag würde Image-Namen veröffentlichen und die Prüfung vom Netz abhängig machen; die Abgabe wird offline geprüft. | D-10, signing.md |
| Was, wenn jemand `kubectl apply` direkt ausführt? | Dann umgeht er die Signaturprüfung der Pipeline. Admission-Control (Kyverno) wäre die Lösung, sie ist ein Zusatzziel (#45, D-05). | Kapitel e |
| Wer wird Admin? | Der erste, der sich nach dem Deployment einloggt (Vorgabe §4); deshalb der eigene Login direkt nach `make up`. | D-07, roles-and-permissions.md |
| Woher wisst ihr, dass das Gate wirklich blockiert? | Drei absichtlich fehlgeschlagene Läufe, jeder blockiert aus genau dem erwarteten Grund; ein echter Lauf wurde ebenfalls blockiert. | Schritt 3, quality-gate.md |
| Warum Traefik statt ingress-nginx? | ingress-nginx wird eingestellt. | ADR-005 |
| Wie ist die Evidence organisiert? | `evidence/<image>/<typ>/<lauf>-<sha>-<datei>`, nichts wird überschrieben; vor der Abgabe auf `main` übernommen. | Doku Kapitel f, D-09 |
| Was war das größte Problem? | Der erste echte Pipeline-Lauf fand sechs Fehler, die lokal nicht auffielen; die Scanner scannten ihre eigenen Berichte. | Doku Kapitel g |
| Was würdet ihr in Produktion anders machen? | Zertifikat einer echten CA, mTLS im Cluster, verschlüsselte Volumes, Admission-Control, Pflicht-Statusprüfungen im Ruleset. | Kapitel e |

## 5. Rückfall-Aufnahmen

Für jeden Schritt eine kurze Bildschirmaufnahme (Windows: Xbox Game Bar mit `Win` + `G`, oder OBS), jeweils auf einem **frisch gestarteten** Cluster aufgenommen. Große Dateien nicht ins Repository, sondern auf USB-Stick und in das Team-Laufwerk.

| Datei | Inhalt | Aufgenommen | Von |
| :--- | :--- | :--- | :--- |
| `01-make-up.mp4` | `make up` bis `Ready` | offen | |
| `02-smoke.mp4` | `make smoke` | offen | |
| `03-gate-secret.mp4` | Lauf `secret` im Browser, Zusammenfassung | offen | |
| `04-cosign.mp4` | `cosign verify` und `cosign tree` | offen | |
| `05-netpol.mp4` | `make verify` | offen | |
| `06-securitycontext.mp4` | `securityContext` und Pod-Check | offen | |

## 6. Probe mit der Stoppuhr

Mindestens zwei vollständige Durchläufe, beide mit Stoppuhr und laufender Demo. Ergebnis hier eintragen. **Bisher nicht durchgeführt.**

| Datum | Durchlauf | Gesamtzeit | Folien | Demo | Probleme |
| :--- | :--- | :--- | :--- | :--- | :--- |
| offen | 1 | | | | |
| offen | 2 | | | | |
