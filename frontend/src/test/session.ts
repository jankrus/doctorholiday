import { vi } from 'vitest';
import type { Role, SessionInfo } from '../api/client';

export function activeSession(role: Role): SessionInfo {
  return {
    state: 'ACTIVE',
    user: {
      id: '00000000-0000-4000-8000-000000000001',
      email: 'user@example.test',
      role,
      mfaEnabled: role !== 'PATIENT',
    },
  };
}

/** A patient who has neither enabled MFA nor declined the offer yet (BR-26). */
export function patientWithOffer(): SessionInfo {
  const session = activeSession('PATIENT');
  return { ...session, user: session.user && { ...session.user, mfaOfferPending: true } };
}

export const apiError = (code: string, status: number) =>
  Response.json(
    { error: { code, message: 'Server text.', requestId: '00000000-0000-4000-8000-000000000003' } },
    { status },
  );

type Handler = (
  request: Request,
  setSession: (next: SessionInfo | null) => void,
) => Response | Promise<Response>;

/**
 * Stubs `fetch` so `GET /api/v1/auth/me` returns `session`, or 401 for `null`. Other requests go
 * to `handlers` by `METHOD /path` or `/path` (e.g. `{ 'PUT /api/v1/settings': ... }`), or get
 * 404. A handler can change the session, as the backend does on login, MFA or logout.
 */
export function stubSession(initial: SessionInfo | null, handlers: Record<string, Handler> = {}) {
  let session = initial;
  const setSession = (next: SessionInfo | null) => {
    session = next;
  };
  const fetchMock = vi.fn(async (request: Request) => {
    const { pathname } = new URL(request.url);
    if (pathname !== '/api/v1/auth/me') {
      const handler = handlers[`${request.method} ${pathname}`] ?? handlers[pathname];
      return handler?.(request, setSession) ?? new Response(null, { status: 404 });
    }
    return session
      ? Response.json(session)
      : Response.json(
          {
            error: {
              code: 'UNAUTHENTICATED',
              message: 'Login required.',
              requestId: '00000000-0000-4000-8000-000000000002',
            },
          },
          { status: 401 },
        );
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}
