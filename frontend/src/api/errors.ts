import type { ApiError } from './client';

type ErrorCode = ApiError['error']['code'];

export const GENERIC_ERROR_MESSAGE = 'Etwas ist schiefgelaufen. Bitte versuchen Sie es erneut.';

// Texts are fixed here; the server's `message` is never shown, so nothing it returns can leak
// into the UI. Feature-specific codes are added by the tickets that use them.
const MESSAGES: Partial<Record<ErrorCode, string>> = {
  VALIDATION_ERROR: 'Bitte überprüfen Sie Ihre Eingaben.',
  UNAUTHENTICATED: 'Bitte melden Sie sich an, um fortzufahren.',
  INVALID_CREDENTIALS: 'E-Mail-Adresse oder Passwort ist falsch.',
  INVALID_MFA_CODE: 'Der Code ist ungültig oder abgelaufen. Bitte versuchen Sie es erneut.',
  MFA_REQUIRED: 'Bitte bestätigen Sie zuerst Ihre Anmeldung mit dem zweiten Faktor.',
  MFA_ALREADY_ENABLED: 'Die Zwei-Faktor-Authentifizierung ist bereits eingerichtet.',
  FORBIDDEN: 'Dazu sind Sie nicht berechtigt.',
  NOT_FOUND: 'Dieser Eintrag wurde nicht gefunden.',
  CONFLICT:
    'Die Daten wurden inzwischen geändert. Bitte laden Sie die Seite neu und versuchen Sie es erneut.',
  PAYLOAD_TOO_LARGE: 'Die Anfrage ist zu groß.',
  RATE_LIMITED:
    'Zu viele Versuche. Bitte warten Sie einen Moment und versuchen Sie es dann erneut.',
  SERVICE_UNAVAILABLE:
    'Der Dienst ist vorübergehend nicht erreichbar. Bitte versuchen Sie es später erneut.',
};

/** Maps any error (API error body, network failure, anything else) to a generic user-facing text. */
export function errorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'error' in error) {
    const { error: body } = error as { error: unknown };
    if (typeof body === 'object' && body !== null && 'code' in body) {
      return MESSAGES[(body as { code: ErrorCode }).code] ?? GENERIC_ERROR_MESSAGE;
    }
  }
  return GENERIC_ERROR_MESSAGE;
}
