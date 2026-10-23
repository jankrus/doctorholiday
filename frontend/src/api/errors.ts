import type { ApiError } from './client';

type ErrorCode = ApiError['error']['code'];

export const GENERIC_ERROR_MESSAGE = 'Something went wrong. Please try again.';

// Texts are fixed here; the server's `message` is never shown, so nothing it returns can leak
// into the UI. Feature-specific codes are added by the tickets that use them.
const MESSAGES: Partial<Record<ErrorCode, string>> = {
  VALIDATION_ERROR: 'Please check your input.',
  UNAUTHENTICATED: 'Please log in to continue.',
  INVALID_CREDENTIALS: 'E-mail or password is incorrect.',
  FORBIDDEN: 'You are not allowed to do this.',
  NOT_FOUND: 'This item was not found.',
  CONFLICT: 'This change conflicts with the current state. Please reload and try again.',
  PAYLOAD_TOO_LARGE: 'The request is too large.',
  RATE_LIMITED: 'Too many attempts. Please wait a moment and try again.',
  SERVICE_UNAVAILABLE: 'The service is temporarily unavailable. Please try again later.',
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
