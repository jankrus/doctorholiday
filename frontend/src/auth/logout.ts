import { redirect } from 'react-router';
import { api } from '../api/client';

/**
 * Ends the session on the server, which also clears the HttpOnly cookie. The frontend keeps no
 * session state of its own: the next navigation asks `GET /auth/me` again.
 */
export async function logoutAction() {
  try {
    await api.POST('/api/v1/auth/logout');
  } catch {
    // Network failure: the session stays valid until it expires; the guards then show it again.
  }
  return redirect('/login?loggedOut');
}
