import createClient from 'openapi-fetch';
import type { components, paths } from './schema';

export type Role = components['schemas']['Role'];
export type SessionInfo = components['schemas']['SessionInfo'];
export type ApiError = components['schemas']['Error'];

/**
 * Typed client for the API contract in `backend/openapi.yaml` (regenerate with `npm run gen:api`).
 *
 * Requests only ever go to the page's own origin: ingress-nginx (or the Vite dev proxy) routes
 * `/api` to the backend. The session lives in an HttpOnly cookie that the browser attaches; the
 * frontend never reads or stores it.
 *
 * MVP-TEMP: no CSRF token is sent yet. Once #19 settles the mechanism (token or Origin check),
 * add it here as middleware for state-changing requests.
 */
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  credentials: 'include',
  // Resolved per call so tests can stub the global fetch.
  fetch: (request) => fetch(request),
});
