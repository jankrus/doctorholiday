import { describe, expect, it } from 'vitest';
import {
  normalizeRecoveryCode,
  normalizeTotpCode,
  passwordLength,
  recoveryCodeError,
  totpCodeError,
  validatePracticeSettings,
  validateRegistration,
} from './validation';

const valid = {
  displayName: '',
  email: 'erika@example.test',
  password: 'correct horse battery',
  confirmPassword: 'correct horse battery',
};

describe('validateRegistration', () => {
  it('accepts valid input', () => {
    expect(validateRegistration(valid)).toBeNull();
  });

  it.each([
    [{ email: '' }, 'email', 'Bitte geben Sie Ihre E-Mail-Adresse ein.'],
    [{ email: 'erika@' }, 'email', 'Bitte geben Sie eine gültige E-Mail-Adresse ein.'],
    [
      { email: `${'a'.repeat(250)}@x.de` },
      'email',
      'Bitte geben Sie eine gültige E-Mail-Adresse ein.',
    ],
    [
      { password: 'a'.repeat(11), confirmPassword: 'a'.repeat(11) },
      'password',
      'mindestens 12 Zeichen',
    ],
    [
      { password: 'a'.repeat(129), confirmPassword: 'a'.repeat(129) },
      'password',
      'höchstens 128 Zeichen',
    ],
    [
      { confirmPassword: 'something else' },
      'confirmPassword',
      'Die Passwörter stimmen nicht überein.',
    ],
    [{ displayName: 'a'.repeat(101) }, 'displayName', 'höchstens 100 Zeichen'],
    [{ displayName: '<script>' }, 'displayName', 'Spitze Klammern'],
    [{ displayName: 'Erika\u0007' }, 'displayName', 'Spitze Klammern'],
  ])('rejects %o', (change, field, message) => {
    const errors = validateRegistration({ ...valid, ...change });
    expect(errors?.[field as keyof typeof errors]).toContain(message);
  });

  it('counts the password length in code points like the backend', () => {
    const emoji = '🔒'.repeat(12);
    expect(emoji.length).toBe(24);
    expect(passwordLength(emoji)).toBe(12);
    expect(validateRegistration({ ...valid, password: emoji, confirmPassword: emoji })).toBeNull();
  });
});

describe('MFA codes', () => {
  it('accepts six digits, also with spaces', () => {
    expect(totpCodeError(normalizeTotpCode(' 123 456 '))).toBeUndefined();
    expect(totpCodeError('12345')).toBeDefined();
    expect(totpCodeError('12345a')).toBeDefined();
  });

  it('accepts recovery codes in any case', () => {
    expect(recoveryCodeError(normalizeRecoveryCode(' ABCDE-FGH27 '))).toBeUndefined();
    expect(recoveryCodeError('abcde-fgh18')).toBeDefined(); // 1 and 8 are not Base32
    expect(recoveryCodeError('abcdefghij')).toBeDefined();
  });
});

describe('validatePracticeSettings', () => {
  const input = {
    practiceName: 'Praxis',
    cancellationDeadlineHours: '24',
    appointmentMinutes: '15',
  };

  it('converts valid input to numbers', () => {
    expect(validatePracticeSettings(input)).toEqual({
      value: { practiceName: 'Praxis', cancellationDeadlineHours: 24, appointmentMinutes: 15 },
    });
  });

  it.each([
    [{ practiceName: '' }, 'practiceName'],
    [{ practiceName: 'a'.repeat(101) }, 'practiceName'],
    [{ practiceName: 'Praxis <b>' }, 'practiceName'],
    [{ cancellationDeadlineHours: '-1' }, 'cancellationDeadlineHours'],
    [{ cancellationDeadlineHours: '169' }, 'cancellationDeadlineHours'],
    [{ cancellationDeadlineHours: '1.5' }, 'cancellationDeadlineHours'],
    [{ appointmentMinutes: '4' }, 'appointmentMinutes'],
    [{ appointmentMinutes: '241' }, 'appointmentMinutes'],
    [{ appointmentMinutes: '' }, 'appointmentMinutes'],
  ])('rejects %o', (change, field) => {
    const result = validatePracticeSettings({ ...input, ...change });
    expect('errors' in result && Object.keys(result.errors)).toEqual([field]);
  });
});
