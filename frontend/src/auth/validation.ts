// Client-side checks that mirror the API contract (`backend/openapi.yaml`). They only give early
// feedback; the server validates every request again and stays authoritative.

export const PASSWORD_MIN_LENGTH = 12; // BR-01
export const PASSWORD_MAX_LENGTH = 128;
const EMAIL_MAX_LENGTH = 254;
const DISPLAY_NAME_MAX_LENGTH = 100; // also the practice name

// Same rule as the `DisplayName` and `practiceName` schemas: no control characters, no angle brackets.
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

const TOTP_CODE = /^[0-9]{6}$/;
const RECOVERY_CODE = /^[a-z2-7]{5}-[a-z2-7]{5}$/;

/** Apps often show the code in two groups ("123 456"); spaces are dropped before checking. */
export function normalizeTotpCode(value: string): string {
  return value.replace(/\s/g, '');
}

export function normalizeRecoveryCode(value: string): string {
  return value.trim().toLowerCase();
}

export function totpCodeError(code: string): string | undefined {
  return TOTP_CODE.test(code)
    ? undefined
    : 'Bitte geben Sie den 6-stelligen Code aus Ihrer App ein.';
}

export function recoveryCodeError(code: string): string | undefined {
  return RECOVERY_CODE.test(code)
    ? undefined
    : 'Bitte geben Sie einen Wiederherstellungscode im Format xxxxx-xxxxx ein.';
}

export type PracticeSettingsInput = {
  practiceName: string;
  cancellationDeadlineHours: string;
  appointmentMinutes: string;
};

export type PracticeSettingsValue = {
  practiceName: string;
  cancellationDeadlineHours: number;
  appointmentMinutes: number;
};

function wholeNumberIn(value: string, min: number, max: number): number | undefined {
  if (!/^\d+$/.test(value)) return undefined;
  const number = Number(value);
  return number >= min && number <= max ? number : undefined;
}

/** BR-18: name 1–100 characters, deadline 0–168 hours, appointment length 5–240 minutes. */
export function validatePracticeSettings(
  input: PracticeSettingsInput,
): { errors: FieldErrors<keyof PracticeSettingsInput> } | { value: PracticeSettingsValue } {
  const errors: FieldErrors<keyof PracticeSettingsInput> = {};

  if (!input.practiceName) {
    errors.practiceName = 'Bitte geben Sie den Namen der Praxis ein.';
  } else if (input.practiceName.length > DISPLAY_NAME_MAX_LENGTH) {
    errors.practiceName = `Bitte verwenden Sie höchstens ${DISPLAY_NAME_MAX_LENGTH} Zeichen.`;
  } else if (DISPLAY_NAME_FORBIDDEN.test(input.practiceName)) {
    errors.practiceName = 'Spitze Klammern (< >) sind nicht erlaubt.';
  }

  const hours = wholeNumberIn(input.cancellationDeadlineHours.trim(), 0, 168);
  if (hours === undefined) {
    errors.cancellationDeadlineHours = 'Bitte geben Sie eine ganze Zahl von 0 bis 168 ein.';
  }
  const minutes = wholeNumberIn(input.appointmentMinutes.trim(), 5, 240);
  if (minutes === undefined) {
    errors.appointmentMinutes = 'Bitte geben Sie eine ganze Zahl von 5 bis 240 ein.';
  }

  if (hours === undefined || minutes === undefined || Object.keys(errors).length > 0) {
    return { errors };
  }
  return {
    value: {
      practiceName: input.practiceName,
      cancellationDeadlineHours: hours,
      appointmentMinutes: minutes,
    },
  };
}
