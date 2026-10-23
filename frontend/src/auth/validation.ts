// Client-side checks that mirror the API contract (`backend/openapi.yaml`). They only give early
// feedback; the server validates every request again and stays authoritative.

export const PASSWORD_MIN_LENGTH = 12; // BR-01
export const PASSWORD_MAX_LENGTH = 128;
const EMAIL_MAX_LENGTH = 254;
const DISPLAY_NAME_MAX_LENGTH = 100;

// Same rule as the `DisplayName` schema: no control characters and no angle brackets.
// eslint-disable-next-line no-control-regex
const DISPLAY_NAME_FORBIDDEN = /[\u0000-\u001f\u007f<>]/;

/**
 * Length in Unicode code points, as the backend counts it. `string.length` counts UTF-16 units,
 * so an emoji would count twice.
 */
export function passwordLength(password: string): number {
  return [...password].length;
}

export function isPasswordLengthValid(password: string): boolean {
  const length = passwordLength(password);
  return length >= PASSWORD_MIN_LENGTH && length <= PASSWORD_MAX_LENGTH;
}

export type RegistrationInput = {
  email: string;
  password: string;
  confirmPassword: string;
  displayName: string;
};

export type FieldErrors<K extends string> = Partial<Record<K, string>>;

/** Field errors in form order, or `null` if the input may be sent. */
export function validateRegistration(
  input: RegistrationInput,
): FieldErrors<keyof RegistrationInput> | null {
  const errors: FieldErrors<keyof RegistrationInput> = {};

  if (input.displayName.length > DISPLAY_NAME_MAX_LENGTH) {
    errors.displayName = `Bitte verwenden Sie höchstens ${DISPLAY_NAME_MAX_LENGTH} Zeichen.`;
  } else if (DISPLAY_NAME_FORBIDDEN.test(input.displayName)) {
    errors.displayName = 'Spitze Klammern (< >) sind nicht erlaubt.';
  }

  if (!input.email) {
    errors.email = 'Bitte geben Sie Ihre E-Mail-Adresse ein.';
  } else if (input.email.length > EMAIL_MAX_LENGTH || !/^[^\s@]+@[^\s@]+$/.test(input.email)) {
    errors.email = 'Bitte geben Sie eine gültige E-Mail-Adresse ein.';
  }

  const length = passwordLength(input.password);
  if (length < PASSWORD_MIN_LENGTH) {
    errors.password = `Bitte verwenden Sie mindestens ${PASSWORD_MIN_LENGTH} Zeichen.`;
  } else if (length > PASSWORD_MAX_LENGTH) {
    errors.password = `Bitte verwenden Sie höchstens ${PASSWORD_MAX_LENGTH} Zeichen.`;
  }

  if (input.confirmPassword !== input.password) {
    errors.confirmPassword = 'Die Passwörter stimmen nicht überein.';
  }

  return Object.keys(errors).length > 0 ? errors : null;
}
