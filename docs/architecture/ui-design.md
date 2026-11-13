# UI design guide

How the Doctor Holiday frontend looks and why. This guide grows with each screen. It started with `/login` and
`/register` (#24), which act as the reference implementation: other screens adopt the patterns below once they have
been reviewed there. The patient screens (#25) added the app shell and the booking patterns (sections 6 and 7).

Built on Radix Themes ([ADR-004](adr/ADR-004-frontend-libraries.md)). Everything below uses the theme's tokens
(`--accent-*`, `--gray-*`, `--space-*`, `--radius-*`), so a palette or dark-mode change happens in one place.

## 1. Principles

| Principle | Meaning in practice |
| :--- | :--- |
| **Calm** | Soft green tints, plenty of white space, one primary action per screen. Patients often open the app while unwell or stressed; nothing should feel loud or urgent unless it is. |
| **Clear** | Short sentences, labels above inputs, errors that say what to do next. Users range from teenagers to elderly patients. |
| **Trustworthy** | Consistent look on every screen, honest wording (no promises the system does not keep), no third-party content. |
| **Accessible** | WCAG 2.2 AA as the target: contrast, keyboard use, screen reader labels, 40 px touch targets. |
| **Secure by design** | The design must not weaken the security controls: no inline styles, no external assets, no server texts in the UI (section 8). |

## 2. Colour

**Accent: Radix `jade`. Gray: Radix `sage`.** Set once on `<Theme>` in `frontend/src/main.tsx`.

Why green: it is the colour most associated with health, nature and calm, it is easy on the eyes over long
viewing, and it reads as positive. Why `jade` among the Radix greens:

| Option | Verdict |
| :--- | :--- |
| `green`, `grass` | Saturated "success" greens. Every button would look like a confirmation, and success messages would lose their meaning. |
| `teal`, `cyan` | The skeleton's default. Leans blue and feels colder and more technical. |
| `mint` | Very light; its solid step is too pale for white button text. |
| **`jade`** | A cool, slightly blue-tinted green: clean and clinical but friendly, and clearly different from error red for colour-blind users when paired with icons. |

`sage` is Radix's gray tuned for green accents. Neutral surfaces and text get a faint green tint, so they belong to
the same family as the accent instead of clashing with it (as a pure or blue-gray would).

### How the 12 steps are used

| Steps | Use | Example |
| :--- | :--- | :--- |
| 1-2 | App and panel backgrounds | Page background, start of the brand panel gradient |
| 3-5 | Subtle fills, tints, hover states | Brand panel gradient end, decorative circles (alpha 5) |
| 6-8 | Borders, focus rings | Panel divider (alpha 5), outline circle (alpha 6) |
| 9-10 | Solid fills | Primary button, logo tile (darkened, see below) |
| 11 | Low-contrast text, icons, links | Icons, met requirements, links |
| 12 | High-contrast text | Brand name, claim |

### Contrast (WCAG 2.2 AA: 4.5:1 for text)

Radix scales are tuned for APCA, and some step combinations miss the WCAG 2 ratio. Measured for the light theme:

| Pair | Radix default | What we use |
| :--- | :--- | :--- |
| White on jade 9 (primary button) | 3.2:1 ✗ | Jade 9/10 overridden to `#1c8164` / `#177a5e` in `global.css`: 4.8:1 / 5.3:1 |
| Jade 11 on white (links, met requirements) | 4.7:1 ✓ | unchanged |
| Jade 11 on jade 3-4 (brand panel texts) | 3.9-4.2:1 ✗ | Gray 11 instead: ≥ 4.5:1 on every gradient step |
| Step 11 on step 3 (soft callouts) | ≈ 4.2:1 ✗ | Callouts use `highContrast` (step 12 text) |
| Jade 12 on jade 4 (brand claim, highlight titles) | 10.2:1 ✓ | unchanged |

Rule: text on a tinted surface uses step 12 or gray 11; accent 11 only on white or step 1-2.

### Semantic colours

- **Accent (jade)**: primary actions, links, confirmations (`role="status"` callouts) and met requirements. A separate
  "success green" is not needed and would compete with the accent.
- **Red**: errors (`role="alert"` callouts, field errors) and the confirm button of a destructive action („Termin
  absagen“ in its confirmation dialog). Never decorative.
- **Amber**: things the patient must know before acting: an appointment inside the change deadline, the fasting
  reminder (BR-10), the open-appointment limit (BR-09). Always `highContrast` or step 11 on white, always with an
  icon.
- **Gray**: secondary text, hints, unmet requirements.

Colour never carries meaning alone: every error has an icon and text, every met requirement turns into a tick.

## 3. Typography

- **Font: the system font stack** (Radix default: San Francisco, Segoe UI, Roboto, …). No web font, because it
  would have to be loaded from a third party (blocked by the CSP `default-src 'self'` of #27, and embedding Google
  Fonts from their servers violates the GDPR, LG München I, 3 O 17493/20) or bundled (more bytes, no real gain).
  System fonts render sharply and look familiar to users on every device.
- **Scale** (Radix `size`):

  | Element | Size | Weight |
  | :--- | :--- | :--- |
  | Page title (`h1`) on auth screens | 7 (German compounds such as „Wiederherstellungscodes“ need the room) | bold |
  | Brand claim | 8 | bold, accent 12 |
  | Intro text below the title | 3 | regular, gray |
  | Labels | 2 | medium |
  | Body, hints, errors, links in text | 2 | regular |

- **Normal German capitalisation** in titles and buttons ("Konto erstellen"); no English-style title case.
- Large headings get slight negative letter spacing (`-0.02em`) and `text-wrap: balance` to avoid lone words.

## 4. Shape, spacing and depth

- **Radius `large`** on the theme: rounded corners feel softer and friendlier, fitting a health context.
- **Spacing** uses the Radix scale only (`--space-1` … `--space-9`, or `gap`/`p` props):

  | Between | Space |
  | :--- | :--- |
  | Label and input, input and hint | 2 |
  | Form fields | 5 |
  | Page sections (title, message, form, footer links) | 6 |
  | Panel padding | 5 (mobile), 8 (desktop) |

- **Depth** is used sparingly: flat surfaces, a single `--shadow-2` on the highlight icons. Separation comes from
  tint and borders, not shadows.

## 5. Icons and imagery

- **Icons** are a small in-repo set in `frontend/src/components/icons.tsx`: line icons on a 24 px grid, stroke
  1.75, round caps, `currentColor`. No icon package, so the SBOM stays small (ADR-004). Icons are `aria-hidden`; the
  text next to them or an `aria-label` carries the meaning.
- **Logo** (`BrandMark`): a rounded medical cross on a jade tile, drawn as inline SVG and coloured through CSS
  classes with theme tokens.
- **No photos or stock illustrations.** Decoration is abstract and made with CSS (soft gradients, circles). It
  keeps the bundle small, needs no external hosting and avoids the generic "smiling doctor" look.

## 6. Layout patterns

### Split screen (auth screens)

Used by `AuthLayout` for every step before the app: `/login`, `/register`, `/mfa` and `/setup`.

```text
≥ 900 px                                   < 900 px
┌──────────────┬─────────────────────┐     ┌─────────────────────┐
│ Logo         │                     │     │ Logo (brand header) │
│              │   Title             │     ├─────────────────────┤
│              │   Intro             │     │ Title               │
│ Claim        │   [Form]            │     │ Intro               │
│ Highlights   │   Footer links      │     │ [Form]              │
│          ◯   │                     │     │ Footer links        │
└──────────────┴─────────────────────┘     └─────────────────────┘
   5 fr (≥ 380 px)      7 fr
```

- **Brand panel**: light jade gradient (accent 2 → 4) with the logo at the top and, on wide screens, a claim and
  three highlights at the bottom. It explains what the app is for before users commit to an account.
- **Form column**: max. 420 px wide (comfortable line length, short eye travel between label and input), vertically
  centred on wide screens.
- **Mobile first**: on narrow screens the panel collapses to a header with only the logo, so the form is visible
  without scrolling.

### App shell

`AppLayout` for everything after login (#25):

```text
┌───────────────────────────────────────────────────────────┐
│ [+] Doctor Holiday │ Praxis am Park        (EM) Name  Abmelden │  white header, gray border
│ Meine Termine   Termin buchen                             │  TabNav (only for roles with > 1 area)
├───────────────────────────────────────────────────────────┤
│                                                           │  gray 2 page background,
│   Page title, intro, primary action                       │  white cards on it
│   [Cards …]                                               │
└───────────────────────────────────────────────────────────┘
```

- **Header**: logo (links to the start page), the practice name from the settings (A26; hidden below 640 px and when
  it is still the default), the account's initials in an `Avatar`, its name or e-mail (hidden below 640 px) and a
  visible „Abmelden“ button. A visible button, not a menu, so nobody has to search for it.
- **Navigation**: Radix `TabNav` below the header with the role's areas; the current one is marked
  (`aria-current="page"`). Roles with a single area get no tabs.
- **Content**: `Container size="3"` (max. 880 px), gray 2 background so white cards stand out without shadows.
- **Data**: the layout's loader (`id: 'app'`) reads the practice settings once; pages read them with
  `usePracticeSettings()` and still work if the request fails (they then hide only the deadline hints).

## 7. Component and form patterns

| Pattern | Component | Rules |
| :--- | :--- | :--- |
| Field | `FormField` | Label above the input; "(optional)" marker instead of an asterisk on required fields; one message line below: the hint, replaced by the error when there is one. Wires `id`, `aria-invalid` and `aria-describedby`. |
| Password | `PasswordField` | Show/hide toggle (`aria-pressed`), so long passphrases can be checked. Only switches the input type. |
| Live checklist | `Requirement` | Rules that can be met while typing (password length, passwords match). Gray dot → jade tick. Positive feedback only; no red while the user is still typing. |
| Page title | `PageHeader` | `h1` and one intro paragraph in gray: what this page is for and what happens next. |
| Page message | `Notice` (Radix `Callout`) | Above the form, below the intro. Errors: red, `role="alert"`. Confirmations: accent, `role="status"`. Always with an icon, always `highContrast`. |
| Code input | `OtpInput` (app codes), `CodeInput` in `MfaPage` | One box per digit, two groups of three like the apps show it. Focus moves on with each digit, Backspace goes back, arrows navigate, a pasted or autofilled code fills all boxes; only digits are accepted. Screen readers get one labelled group with „Ziffer 1 von 6“ … per box. Recovery codes keep a single monospace field. After a wrong code the input is cleared and focused. No auto-submit: the user confirms with the button. |
| Steps | `.mfa-steps` | Numbered accent circles joined by a thin line, for tasks that happen outside the app (scan with the phone, then type the code). |
| QR code | `QrCode` | Always black on white in a card, whatever the theme (scanners need contrast). Generated locally; the key for manual entry sits in a `<details>` below it, grouped in fours, with a copy button. |
| One-time secrets | `RecoveryCodes` in `MfaPage` | Shown once in a card with „Codes kopieren“ and „Herunterladen“ (.txt). „Weiter“ stays disabled until the user confirms they saved them. Held only in component state. |
| Copy | `CopyButton` | Soft button, label turns into „Kopiert“ with a tick for two seconds (announced politely). |
| Leave the flow | `LogoutButton` / `LeaveEnrollment` | Ghost button at the end of every step page, so nobody is stuck in a half-finished login. Mandatory steps offer „Abbrechen und abmelden“; the optional MFA offer for patients (BR-26) offers „Ohne zweiten Faktor fortfahren“ and says it will not ask again. |
| Primary action | Radix `Button` `size="3"` | One per form, solid, full width, at the end of the form. Shows a spinner (`loading`) while submitting, which also blocks double submits. |
| Secondary navigation | Radix `Link` | Below the form, as a sentence: „Noch kein Konto? Jetzt registrieren“. |
| Inputs | Radix `TextField` `size="3"` | 40 px high: a comfortable touch target. Numbers get their unit inside the field („Stunden“, „Minuten“) and the allowed range in the hint. |
| App page title | `PatientPageHeader` | `h1` (size 7, 8 on wide screens), one intro sentence, optional primary action on the right (stacked on mobile) and an optional „← Meine Termine“ link above. |
| Availability browser | `AvailabilityBrowser` | Doctor `Select` („Alle Ärztinnen und Ärzte“ first), a highlighted „Nächster freier Termin“ card with a one-click „Diesen Termin wählen“, then one card per week: previous/next week buttons (disabled outside today … 365 days, BR-23), seven day `RadioCards` with the number of free times (days without any are disabled; they scroll sideways on phones), and the chosen day's times as buttons grouped into Vormittag / Nachmittag / Abend. With „Alle“ each time button names the doctor or „2 zur Auswahl“. An empty week offers a jump to the week of the next free time. The first free day is preselected. |
| Time dialog | `TimeDialog` | Radix `Dialog` that confirms a chosen time: day, time range, doctor (as `RadioCards` if several are free), reason as eight `RadioCards` (booking only; visible at once, no dropdown to discover), the fasting hint for „Blutabnahme (nüchtern)“, and the online change deadline as a sentence (amber if the time already lies inside it). Rescheduling shows the old time struck through and says the old appointment stays until the new one is confirmed. Success replaces the form with a confirmation (tick, time, doctor, deadline). A `409` replaces it with the error and „Andere Uhrzeit wählen“, while the route reloads the free times behind it. |
| Appointment card | `AppointmentCard` | Calendar tile (month, day, weekday), day, time range, doctor, reason badge plus status badges (nüchtern, booked or cancelled by the practice). The next appointment is labelled „Nächster Termin“. A footer line says until when it can be changed online, or, inside the deadline (BR-11), says so in amber and hides the buttons. Past and cancelled appointments use the muted variant in a collapsed `<details>` history. |
| Confirm a destructive action | Radix `AlertDialog` | Title as a question („Termin absagen?“), what exactly happens, a softer alternative where one exists („Verschieben Sie den Termin …“), then „Termin behalten“ (default focus, soft gray) and the red confirm button. Errors appear inside the dialog. |

### Form behaviour

1. **Validate on submit**, not on blur: users are not interrupted while filling in the form. `noValidate` replaces
   the browser's inconsistent bubbles with our own messages.
2. After a failed submit, **focus moves to the first invalid field**; its error is announced via `aria-describedby`.
3. **Client checks mirror the API contract** (`frontend/src/auth/validation.ts`) and only give early feedback. The
   server stays authoritative. Password length is counted in code points like the backend.
4. **`autocomplete` attributes** on every field (`username`, `email`, `current-password`, `new-password`, `name`),
   so password managers work. That matters because BR-01 encourages long passphrases.
5. **Failed login**: the e-mail stays, the password is cleared and focused.
6. Submission uses React Router actions (`<Form method="post">`, or a fetcher where one page holds several steps),
   so pending and error states follow one pattern on every screen.
7. **Defaults are prefilled** where the system has sensible ones (practice setup), so the common case is one click.

## 8. Security-driven design rules

| Rule | Reason |
| :--- | :--- |
| Styles live in CSS files using theme tokens; no `style` attributes, no CSS-in-JS. | Keeps a strict `style-src` CSP possible (#27). |
| No external fonts, images, icons or scripts. | CSP `default-src 'self'`, no tracking by third parties, GDPR. |
| User-facing error texts come from a fixed local map (`api/errors.ts`), never from the server's `message`. | Server details cannot leak into the UI (ADR-004). |
| Login shows one generic error for every failure. | Does not reveal whether an account exists (BR-03). |
| The registration confirmation is worded the same whether or not the e-mail was new. | The API answers `202` either way (BR-02); the UI must not hint otherwise. |
| Nothing from a form is written to `localStorage`/`sessionStorage` or the URL. | Acceptance criterion of #24 (covered by a test); only harmless `?registered` / `?loggedOut` flags are put in the URL. The booking pages add the shown week and the doctor filter (`?week=…&doctor=…`): navigation state, a public doctor ID, no personal data. |
| Names and other server data are rendered as React text only. | No `innerHTML`/`dangerouslySetInnerHTML` (ESLint rule); a test renders a doctor name containing HTML and checks that no element is created (#25). |
| Reasons are categories, never free text. | BR-10: no symptoms or diagnoses are stored, and the field cannot carry injected content. The dialog says so („Details besprechen Sie in der Praxis“). |
| All dates and times are shown in the practice time zone (`Europe/Berlin`). | Working hours are defined there (BR-08); a patient abroad still sees the practice's clock. Week bounds are converted to UTC per date, so DST weeks work. |
| The TOTP secret and recovery codes live only in component state and are shown once. | BR-06, BR-07; they disappear when the user continues. The QR code is drawn locally, never by a web service. |
| MFA is mandatory for practice roles and offered once to patients; only patients can skip it. | BR-05, BR-26. The skip is stored on the account (A36), not in the browser, so it holds on every device. |
| No "forgot password" link that promises a reset. | Password reset by e-mail is out of scope; the page says to contact the practice instead. |

## 9. Language, voice and wording

**The UI is German.** The practice and its patients are in Germany, and patients must understand every step without
effort, including older people and people who are unwell. Code, comments and documentation stay in English.

- **German only, no i18n framework.** Texts are written directly in the components and in the error map
  (`api/errors.ts`). A translation library would add a dependency (SBOM, SCA) for a second language nobody has
  asked for; if one is needed later, the texts are easy to find.
- **`<html lang="de">`**, so screen readers pronounce the texts correctly and browsers hyphenate and spell-check in
  German.
- **Formal address „Sie“**, the norm for a medical practice. Friendly and direct, short sentences, no jargon
  („zweiter Faktor“ is explained on the MFA screen, not assumed).
- **Gender-neutral without special characters**: neutral nouns („Mitarbeitende“, „Praxisteam“) or both forms
  („Patientinnen und Patienten“). No gender star or colon: screen readers read them out awkwardly and they hurt
  readability for some users.
- **One verb per action**: „Anmelden“ (never „Einloggen“ or „Login“), „Registrieren“ / „Konto erstellen“,
  „Abmelden“ (never „Ausloggen“).
- **Errors say what to do**: „Bitte verwenden Sie mindestens 12 Zeichen.“ rather than „Ungültiges Passwort“.
- **Spelling**: „E-Mail-Adresse“, German quotation marks („…“) and the en dash (–) with spaces.
- **Formats** for later screens: dates as `23.10.2026`, times as `14:30 Uhr` (24-hour clock), weekdays written out
  („Freitag, 23. Oktober“). Use `Intl` with the locale `de-DE`, not hand-built strings.

## 10. Rollout and open points

1. **Done**: `/login` and `/register` as the reference.
2. **Done**: `/mfa` (code entry, enrolment with QR code and recovery codes) and `/setup` on the same `AuthLayout` and
   form patterns.
3. **Done**: `AppLayout` (header, navigation, logout) and the patient screens `/appointments`, `/appointments/book`
   and `/appointments/:id/reschedule` (#25).
4. **Next**: staff and admin screens (#26) on the same shell; they can reuse `AvailabilityBrowser`, `TimeDialog`
   and `AppointmentCard`.
5. **Later**: dark mode. All colours are tokens, so it is mostly a matter of setting `appearance` on `<Theme>` and
   checking the brand panel.

Open questions for review: wording of the brand claim and highlights, and whether the name field belongs in
registration.
