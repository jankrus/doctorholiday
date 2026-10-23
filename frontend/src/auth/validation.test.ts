import { describe, expect, it } from 'vitest';
import { passwordLength, validateRegistration } from './validation';

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
