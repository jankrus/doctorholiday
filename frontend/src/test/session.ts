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

/** Stubs `fetch` so `GET /api/v1/auth/me` returns `session`, or 401 for `null`. */
export function stubSession(session: SessionInfo | null) {
  const fetchMock = vi.fn(async (request: Request) => {
    if (new URL(request.url).pathname !== '/api/v1/auth/me') {
      return new Response(null, { status: 404 });
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
