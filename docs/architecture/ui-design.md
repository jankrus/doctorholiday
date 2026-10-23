# UI design guide

How the Doctor Holiday frontend looks and why. This guide grows with each screen. It started with `/login` and
`/register` (#24), which act as the reference implementation: other screens adopt the patterns below once they have
been reviewed there.

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
- **Red**: errors only (`role="alert"` callouts, field errors). Never decorative.
- **Amber**: warnings, reserved for later screens (e.g. "appointment within the cancellation deadline").
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
  | Page title (`h1`) on auth screens | 8 | bold |
  | Brand claim | 8 | bold, accent 12 |
  | Intro text below the title | 3 | regular, gray |
  | Labels | 2 | medium |
  | Body, hints, errors, links in text | 2 | regular |

- **Sentence case** everywhere ("Create your account", not "Create Your Account").
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

Used by `AuthLayout` for `/login` and `/register`; `/mfa` and `/setup` follow next.

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

`AppLayout` (header with product name and account, content below) for everything after login. It still has the
skeleton look and is redesigned once the auth screens are approved (section 10).

## 7. Component and form patterns

| Pattern | Component | Rules |
| :--- | :--- | :--- |
| Field | `FormField` | Label above the input; "(optional)" marker instead of an asterisk on required fields; one message line below: the hint, replaced by the error when there is one. Wires `id`, `aria-invalid` and `aria-describedby`. |
| Password | `PasswordField` | Show/hide toggle (`aria-pressed`), so long passphrases can be checked. Only switches the input type. |
| Live checklist | `Requirement` | Rules that can be met while typing (password length, passwords match). Gray dot → jade tick. Positive feedback only; no red while the user is still typing. |
| Page message | Radix `Callout` | Above the form, below the intro. Errors: red, `role="alert"`. Confirmations: accent, `role="status"`. Always with an icon. |
| Primary action | Radix `Button` `size="3"` | One per form, solid, full width, at the end of the form. Shows a spinner (`loading`) while submitting, which also blocks double submits. |
| Secondary navigation | Radix `Link` | Below the form, as a sentence: "New patient? Create an account". |
| Inputs | Radix `TextField` `size="3"` | 40 px high: a comfortable touch target. |

### Form behaviour

1. **Validate on submit**, not on blur: users are not interrupted while filling in the form. `noValidate` replaces
   the browser's inconsistent bubbles with our own messages.
2. After a failed submit, **focus moves to the first invalid field**; its error is announced via `aria-describedby`.
3. **Client checks mirror the API contract** (`frontend/src/auth/validation.ts`) and only give early feedback. The
   server stays authoritative. Password length is counted in code points like the backend.
4. **`autocomplete` attributes** on every field (`username`, `email`, `current-password`, `new-password`, `name`),
   so password managers work. That matters because BR-01 encourages long passphrases.
5. **Failed login**: the e-mail stays, the password is cleared and focused.
6. Submission uses React Router actions (`<Form method="post">`), so pending and error states follow one pattern on
   every screen.

## 8. Security-driven design rules

| Rule | Reason |
| :--- | :--- |
| Styles live in CSS files using theme tokens; no `style` attributes, no CSS-in-JS. | Keeps a strict `style-src` CSP possible (#27). |
| No external fonts, images, icons or scripts. | CSP `default-src 'self'`, no tracking by third parties, GDPR. |
| User-facing error texts come from a fixed local map (`api/errors.ts`), never from the server's `message`. | Server details cannot leak into the UI (ADR-004). |
| Login shows one generic error for every failure. | Does not reveal whether an account exists (BR-03). |
| The registration confirmation is worded the same whether or not the e-mail was new. | The API answers `202` either way (BR-02); the UI must not hint otherwise. |
| Nothing from a form is written to `localStorage`/`sessionStorage` or the URL. | Acceptance criterion of #24; only a harmless `?registered` flag is put in the URL. |
| No "forgot password" link that promises a reset. | Password reset by e-mail is out of scope; the page says to contact the practice instead. |

## 9. Voice and wording

- **Friendly and direct**, addressing the user as "you". Short sentences, no jargon ("second factor" is explained on
  the MFA screen, not assumed).
- **One verb per action**: "Log in" (never "Sign in"), "Create account" / "register" (never "Sign up"), "Log out".
- **Errors say what to do**: "Use at least 12 characters." rather than "Invalid password".
- **E-mail address**, not "Email" or "Mail".
- UI language is English for now. German, the practice's likely language, would be a separate decision.

## 10. Rollout and open points

1. **Now**: `/login` and `/register` as the reference. Review here first.
2. **Next**: `/mfa` (code entry, enrolment with QR code and recovery codes) and `/setup` on the same `AuthLayout` and
   form patterns.
3. **Then**: redesign `AppLayout` (header, navigation, logout) for the patient, staff and admin areas.
4. **Later**: dark mode. All colours are tokens, so it is mostly a matter of setting `appearance` on `<Theme>` and
   checking the brand panel.

Open questions for review: wording of the brand claim and highlights, whether the name field belongs in
registration, and the UI language.
