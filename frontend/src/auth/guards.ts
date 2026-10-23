import { redirect, type LoaderFunction } from 'react-router';
import type { Role, SessionInfo } from '../api/client';
import { loadSession } from './session';

// Route guards are UX only: they keep users away from screens they cannot use. Every request is
// authorised by the backend regardless of what the frontend shows.

const HOME_BY_ROLE: Record<Role, string> = {
  PATIENT: '/appointments',
  STAFF: '/staff',
  DOCTOR: '/staff',
  ADMIN: '/admin',
};

/** Where a session belongs: its role's start page, `/mfa` until MFA is done, else `/login`. */
export function homePath(session: SessionInfo | null): string {
  if (!session) return '/login';
  if (session.state !== 'ACTIVE' || !session.user) return '/mfa';
  return HOME_BY_ROLE[session.user.role];
}

/** Target to redirect to, or `null` if the session may open a page for `roles`. */
export function protectedRedirect(
  session: SessionInfo | null,
  roles: readonly Role[],
): string | null {
  if (session?.state === 'ACTIVE' && session.user && roles.includes(session.user.role)) {
    return null;
  }
  return homePath(session);
}

export function requireRole(roles: readonly Role[]): LoaderFunction {
  return async () => {
    const target = protectedRedirect(await loadSession(), roles);
    return target ? redirect(target) : null;
  };
}

/** Login and registration: only without a session. */
export const guestOnly: LoaderFunction = async () => {
  const session = await loadSession();
  return session ? redirect(homePath(session)) : null;
};

/** MFA: only while the session still waits for MFA verification or enrolment. */
export const mfaPending: LoaderFunction = async () => {
  const session = await loadSession();
  return homePath(session) === '/mfa' ? null : redirect(homePath(session));
};

export const toHome: LoaderFunction = async () => redirect(homePath(await loadSession()));
