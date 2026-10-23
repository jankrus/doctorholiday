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
    [{ email: '' }, 'email', 'Please enter your e-mail address.'],
    [{ email: 'erika@' }, 'email', 'Please enter a valid e-mail address.'],
    [{ email: `${'a'.repeat(250)}@x.de` }, 'email', 'Please enter a valid e-mail address.'],
    [{ password: 'a'.repeat(11), confirmPassword: 'a'.repeat(11) }, 'password', 'Use at least'],
    [{ password: 'a'.repeat(129), confirmPassword: 'a'.repeat(129) }, 'password', 'Use at most'],
    [{ confirmPassword: 'something else' }, 'confirmPassword', 'The passwords do not match.'],
    [{ displayName: 'a'.repeat(101) }, 'displayName', 'Use at most 100 characters.'],
    [{ displayName: '<script>' }, 'displayName', 'Angle brackets'],
    [{ displayName: 'Erika\u0007' }, 'displayName', 'Angle brackets'],
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
