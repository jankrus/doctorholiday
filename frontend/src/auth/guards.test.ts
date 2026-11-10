import { describe, expect, it } from 'vitest';
import { activeSession, patientWithOffer } from '../test/session';
import { homePath, protectedRedirect } from './guards';

describe('homePath', () => {
  it('sends visitors without a session to the login page', () => {
    expect(homePath(null)).toBe('/login');
  });

  it.each(['MFA_PENDING', 'MFA_ENROLLMENT_REQUIRED'] as const)('sends %s to /mfa', (state) => {
    expect(homePath({ state })).toBe('/mfa');
  });

  it.each([
    ['PATIENT', '/appointments'],
    ['STAFF', '/staff'],
    ['DOCTOR', '/staff'],
    ['ADMIN', '/admin'],
  ] as const)('sends %s to %s', (role, path) => {
    expect(homePath(activeSession(role))).toBe(path);
  });

  it('sends an admin to /setup until the practice settings are saved', () => {
    expect(homePath({ ...activeSession('ADMIN'), setupRequired: true })).toBe('/setup');
  });

  it('sends a patient to /mfa until the optional MFA offer is answered', () => {
    expect(homePath(patientWithOffer())).toBe('/mfa');
  });
});

describe('protectedRedirect', () => {
  it('lets an active session with an allowed role pass', () => {
    expect(protectedRedirect(activeSession('DOCTOR'), ['STAFF', 'DOCTOR'])).toBeNull();
  });

  it('redirects other roles to their own start page', () => {
    expect(protectedRedirect(activeSession('PATIENT'), ['ADMIN'])).toBe('/appointments');
  });

  it('redirects to /login without a session', () => {
    expect(protectedRedirect(null, ['PATIENT'])).toBe('/login');
  });

  it('redirects to /mfa before MFA is verified', () => {
    expect(protectedRedirect({ state: 'MFA_PENDING' }, ['ADMIN'])).toBe('/mfa');
  });

  it('redirects to /setup before the practice setup is done', () => {
    expect(protectedRedirect({ ...activeSession('ADMIN'), setupRequired: true }, ['ADMIN'])).toBe(
      '/setup',
    );
  });

  it('redirects a patient to /mfa while the MFA offer is pending', () => {
    expect(protectedRedirect(patientWithOffer(), ['PATIENT'])).toBe('/mfa');
  });
});
