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

/**
 * Where a session belongs: `/login` without one, `/mfa` until MFA is done, `/setup` while the
 * first admin has not saved the practice settings yet, else its role's start page.
 */
export function homePath(session: SessionInfo | null): string {
  if (!session) return '/login';
  if (session.state !== 'ACTIVE' || !session.user) return '/mfa';
  if (session.setupRequired) return '/setup';
  return HOME_BY_ROLE[session.user.role];
}

/** Target to redirect to, or `null` if the session may open a page for `roles`. */
export function protectedRedirect(
  session: SessionInfo | null,
  roles: readonly Role[],
): string | null {
  if (
    session?.state === 'ACTIVE' &&
    session.user &&
    !session.setupRequired &&
    roles.includes(session.user.role)
  ) {
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

/** A step on the way in: only while the session is at that step, as `homePath` decides. */
function stepPage(path: string): LoaderFunction {
  return async () => {
    const target = homePath(await loadSession());
    return target === path ? null : redirect(target);
  };
}

/** MFA: only while the session still waits for MFA verification or enrolment. */
export const mfaPending = stepPage('/mfa');

/** Practice setup: only for an admin who has not saved the practice settings yet. */
export const setupPending = stepPage('/setup');

export const toHome: LoaderFunction = async () => redirect(homePath(await loadSession()));
