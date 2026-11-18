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
  MFA_NOT_ENABLED:
    'Die Zwei-Faktor-Authentifizierung ist nicht eingerichtet. Bitte starten Sie die Einrichtung neu.',
  FORBIDDEN: 'Dazu sind Sie nicht berechtigt.',
  NOT_FOUND: 'Dieser Eintrag wurde nicht gefunden.',
  CONFLICT:
    'Die Daten wurden inzwischen geändert. Bitte laden Sie die Seite neu und versuchen Sie es erneut.',
  PAYLOAD_TOO_LARGE: 'Die Anfrage ist zu groß.',
  RATE_LIMITED:
    'Zu viele Versuche. Bitte warten Sie einen Moment und versuchen Sie es dann erneut.',
  // Appointments (#25). Both "not available" codes mean the same to a patient: someone was faster.
  TIME_NOT_AVAILABLE:
    'Diese Uhrzeit ist leider nicht mehr frei. Bitte wählen Sie eine andere Uhrzeit.',
  TIME_ALREADY_BOOKED: 'Diese Uhrzeit wurde gerade vergeben. Bitte wählen Sie eine andere Uhrzeit.',
  APPOINTMENT_LIMIT_REACHED:
    'Sie haben bereits 5 offene Termine. Bitte sagen Sie zuerst einen Termin ab, bevor Sie einen neuen buchen.',
  APPOINTMENT_NOT_CANCELLABLE:
    'Dieser Termin kann nicht mehr abgesagt werden. Bitte laden Sie die Seite neu.',
  APPOINTMENT_NOT_RESCHEDULABLE:
    'Dieser Termin kann nicht mehr verschoben werden. Bitte laden Sie die Seite neu.',
  CANCELLATION_DEADLINE_PASSED:
    'Für eine Online-Änderung ist es jetzt zu spät. Bitte wenden Sie sich telefonisch an die Praxis.',
};

/** An API error body, thrown from data helpers so a loader can map it with `errorMessage`. */
export class ApiRequestError extends Error {
  constructor(readonly body: unknown) {
    super('API request failed');
  }
}

/** The error code of an API error body, if it is one. */
export function errorCode(error: unknown): ErrorCode | undefined {
  if (error instanceof ApiRequestError) return errorCode(error.body);
  if (typeof error === 'object' && error !== null && 'error' in error) {
    const { error: body } = error as { error: unknown };
    if (typeof body === 'object' && body !== null && 'code' in body) {
      return (body as { code: ErrorCode }).code;
    }
  }
  return undefined;
}

/** The chosen time was taken or is no longer offered (409): the user should pick another one. */
export function isTimeConflict(error: unknown): boolean {
  const code = errorCode(error);
  return code === 'TIME_NOT_AVAILABLE' || code === 'TIME_ALREADY_BOOKED';
}

/** Maps any error (API error body, network failure, anything else) to a generic user-facing text. */
export function errorMessage(error: unknown): string {
  const code = errorCode(error);
  return (code && MESSAGES[code]) ?? GENERIC_ERROR_MESSAGE;
}
