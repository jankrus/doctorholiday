import { api, type SessionInfo } from '../api/client';

async function fetchSession(): Promise<SessionInfo | null> {
  const { data, response } = await api.GET('/api/v1/auth/me');
  if (data) return data;
  if (response.status === 401) return null;
  throw new Error(`Session lookup failed with status ${response.status}`);
}

let inflight: Promise<SessionInfo | null> | undefined;

/**
 * Current session, or `null` without a valid one. Loaders of one navigation run in parallel and
 * share a single request; the next navigation asks the backend again.
 */
export function loadSession(): Promise<SessionInfo | null> {
  inflight ??= fetchSession().finally(() => {
    inflight = undefined;
  });
  return inflight;
}
