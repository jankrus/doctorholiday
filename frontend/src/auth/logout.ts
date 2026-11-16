import { redirect } from 'react-router';
import { api } from '../api/client';
import { errorMessage } from '../api/errors';
import { toast } from '../components/toastStore';

/**
 * Ends the session on the server, which also clears the HttpOnly cookie. The frontend keeps no
 * session state of its own: the next navigation asks `GET /auth/me` again. The confirmation is a
 * toast raised before the redirect, so nothing about the logout stays in the URL.
 */
export async function logoutAction() {
  try {
    await api.POST('/api/v1/auth/logout');
    toast.success('Sie wurden abgemeldet.');
  } catch {
    // Network failure: the session stays valid until it expires, and the guards show it again.
    toast.error(errorMessage(null));
  }
  return redirect('/login');
}
