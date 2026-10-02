# ADR-001: Technology Stack & DevSecOps Platform

## 1. Context
Im Rahmen der Prüfungsleistung „Security by Design“ (sbd_pruefungsleistung_3er.pdf) wird ein sicheres Terminbuchungssystem für eine Arztpraxis entwickelt[cite: 1]. Der Schwerpunkt liegt auf Sicherheit, reproduzierbaren Lieferketten und dem Deployment in einem lokalen Kubernetes-Cluster[cite: 1]. Die Wahl der Programmiersprachen und Frameworks ist grundsätzlich frei, muss jedoch pro Komponente fundiert begründet und im Hinblick auf Security-Features evaluiert werden[cite: 1]. Da jede nachfolgende Implementierung von diesen Entscheidungen abhängt, legt dieses ADR den vollständigen Anwendungs-Stack, die Basis-Images sowie die Plattform-Werkzeuge fest.

## 2. Considered Options

### 2.1. Frontend
*   **Option A: React (TypeScript) + Vite**
    *   *Vorteile:* Sehr große Community, exzellente Unterstützung durch SAST-Tools (Semgrep), Typsicherheit durch TypeScript. Standardmäßiges Escaping schützt nativ vor den meisten XSS-Angriffen.
    *   *Nachteile:* Erfordert ein separates Build-Setup und eine Webserver-Komponente (Nginx) für das Deployment.
*   **Option B: Vue.js (TypeScript) + Vite**
    *   *Vorteile:* Flache Lernkurve, ebenfalls gute Security-Defaults.
    *   *Nachteile:* SAST-Regelwerke (z. B. für Semgrep) sind für React oft noch feingranularer und ausgereifter.

### 2.2. Backend
*   **Option A: Python (FastAPI)**
    *   *Vorteile:* Extrem schnelle Entwicklung, native und strikte Eingabevalidierung durch Pydantic (verhindert Injection-Angriffe frühzeitig)[cite: 2]. Sehr gutes Ökosystem für Kryptographie (Argon2, TOTP). Distroless-Images für Python sind etabliert.
    *   *Nachteile:* Keine kompilierte Sprache (im Gegensatz zu Go), was die Containergröße minimal erhöht, auch wenn Distroless verwendet wird.
*   **Option B: C# (ASP.NET Core Web API)**
    *   *Vorteile:* Out-of-the-Box starke Security-Mechanismen, Typsicherheit, exzellente *Chiseled*-Images von Microsoft für minimale Angriffsflächen im Cluster.
    *   *Nachteile:* Etwas höherer Boilerplate-Aufwand im Vergleich zu FastAPI.

### 2.3. Datenbank
*   **Option A: PostgreSQL**
    *   *Vorteile:* Industrie-Standard, robuste Zugriffskontrolle, harmoniert perfekt mit Kubernetes Network Policies (Least Privilege)[cite: 3]. Ausgereifte Container-Images (z. B. Alpine-basierte Non-Root-Images) verfügbar.
    *   *Nachteile:* Benötigt etwas mehr Ressourcen als dateibasierte Datenbanken.
*   **Option B: SQLite**
    *   *Vorteile:* Keine Netzwerkfreigaben nötig, minimale Komplexität.
    *   *Nachteile:* Im Kubernetes-Umfeld (mit flüchtigen Pods) schwierig sicher persistent zu betreiben; weniger geeignet für die Demonstration von Network Policies.

### 2.4. Session Management & Auth
*   **Option A: Server-Side Sessions mit HttpOnly-Cookies (Empfohlen)**
    *   *Vorteile:* Session-Identifikatoren sind vor JavaScript (und damit XSS) geschützt. SameSite-Attribute verhindern CSRF-Angriffe zuverlässig.
    *   *Nachteile:* Erfordert State-Management (z. B. in der DB) auf Backend-Seite.
*   **Option B: Stateless JWT (JSON Web Tokens)**
    *   *Vorteile:* Komplett zustandslos, einfache Skalierung.
    *   *Nachteile:* Sichere Speicherung im Browser ist komplex. Werden sie im Local Storage gespeichert, sind sie durch XSS auslesbar; Invalidierung (Logout) vor Ablauf der Lebenszeit ist schwer umsetzbar.

### 2.5. Password Hashing
*   **Option A: Argon2id** (Moderner Standard, speicher- und rechenintensiv, extrem resistent gegen GPU-Cracking).
*   **Option B: bcrypt** (Bewährt und gut, aber älter und auf moderner Hardware etwas anfälliger für Brute-Force als Argon2).

## 3. Decision Outcome

Wir entscheiden uns für die Kombination aus **React** (Frontend), **Python/FastAPI** (Backend) und **PostgreSQL** (Datenbank). 
Als Authentifizierungsmechanismus nutzen wir **Server-Side Sessions mit einem strikten HttpOnly, Secure, SameSite=Strict Cookie**, um Token-Diebstahl durch XSS strukturell auszuschließen. Passwörter werden mit **Argon2id** gehasht. Alle Docker-Images basieren auf gehärteten Minimal-Images (`distroless` oder `alpine` / `unprivileged`) und werden in der Pipeline strikt per Digest (SHA256) gepinnt, um Supply-Chain-Attacken zu verhindern.

### 3.1. Bibliotheken und Versionen

*   **Frontend:**
    *   Framework: React v18
    *   Build-Tool: Vite v5
    *   Linter: ESLint v8
    *   Testing: Vitest
*   **Backend:**
    *   Language: Python 3.12
    *   Framework: FastAPI v0.110+
    *   ORM / Query Layer: SQLAlchemy v2 (mit parametrisierten Queries zur Vermeidung von SQL-Injection)
    *   Validation: Pydantic v2
    *   Auth / Session: Implementierung basierend auf FastAPI-Dependencies und `itsdangerous` oder `fastapi-users`.
    *   Password Hashing: `passlib` (mit `argon2-cffi` v23)
    *   TOTP (MFA): `pyotp` v2.9
    *   Linter / Formatter: `ruff`
    *   Testing: `pytest`
*   **Database:**
    *   Engine: PostgreSQL 16

### 3.2. Container Base Images & Mapping

| Component | Language / Tool | Framework | Base Image (to be pinned by digest) |
| :--- | :--- | :--- | :--- |
| **Frontend** | TypeScript / HTML | React / Nginx | `nginxinc/nginx-unprivileged:alpine` |
| **Backend** | Python 3.12 | FastAPI | `cgr.dev/chainguard/python` (oder `gcr.io/distroless/python3`) |
| **Database** | SQL | PostgreSQL | `postgres:16-alpine` |

### 3.3. DevSecOps Platform Tooling (Pre-decided)
Alle Komponenten durchlaufen die festgelegte CI/CD-Pipeline:
*   **CI/CD:** GitHub Actions
*   **Container Registry:** GHCR (GitHub Container Registry)
*   **Image Signing:** cosign (Schlüsselbasiertes Signieren und Verifizieren im Quality Gate)[cite: 2]
*   **SBOM Erstellung:** Syft[cite: 2]
*   **SAST:** Semgrep (Scannen von React und Python Code)[cite: 2]
*   **SCA & Image Scan:** Trivy[cite: 2]
*   **Secret Scanning:** Gitleaks[cite: 2]
*   **Deployment:** Lokales `kind`-Cluster mit `ingress-nginx` über Makefile-Automatisierung[cite: 4].

## 4. Consequences (Pros & Cons)

*   **Sicherheit (Pros):** Durch die Wahl von FastAPI in Kombination mit Pydantic werden Payloads automatisch auf Typ-Ebene validiert, was die Anforderungen an Secure Coding stark unterstützt[cite: 3]. HttpOnly-Cookies minimieren die Angriffsfläche im Client dramatisch. Distroless- bzw. Alpine-Images verkleinern die Angriffsfläche im Container auf ein Minimum (keine Shell, keine unnötigen Binaries), was im Trivy-SCA-Scan zu einem Report mit nahezu null Schwachstellen führen wird[cite: 2].
*   **Entwicklung (Cons):** Die korrekte Konfiguration von CORS und SameSite-Cookies für lokale Umgebungen (zwischen Frontend-Port und Backend-Port) ist oft fehleranfällig und erfordert saubere Environment-Variablen. Das Fehlen einer Shell in Distroless-Images (Backend) macht das Debugging innerhalb des laufenden Pods im Kubernetes-Cluster schwieriger.