import { describe, expect, it } from 'vitest';
import { GENERIC_ERROR_MESSAGE, errorMessage } from './errors';

const apiError = (code: string, message = 'server text') => ({
  error: { code, message, requestId: '00000000-0000-4000-8000-000000000003' },
});

describe('errorMessage', () => {
  it('maps known codes to fixed texts and ignores the server message', () => {
    const text = errorMessage(apiError('INVALID_CREDENTIALS', 'internal detail'));
    expect(text).toBe('E-Mail-Adresse oder Passwort ist falsch.');
    expect(text).not.toContain('internal detail');
  });

  it.each([
    ['an unmapped code', apiError('INTERNAL_ERROR')],
    ['an unknown code', apiError('SOMETHING_NEW')],
    ['a network failure', new TypeError('Failed to fetch')],
    ['a non-JSON body', '<html>Bad gateway</html>'],
    ['nothing', undefined],
  ])('falls back to the generic text for %s', (_, error) => {
    expect(errorMessage(error)).toBe(GENERIC_ERROR_MESSAGE);
  });
});
