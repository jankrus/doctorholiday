import { describe, expect, it } from 'vitest';
import { activeSession, stubSession } from '../test/session';
import { loadSession } from './session';

describe('loadSession', () => {
  it('asks the own origin with the session cookie', async () => {
    const fetchMock = stubSession(activeSession('PATIENT'));

    await expect(loadSession()).resolves.toEqual(activeSession('PATIENT'));

    expect(fetchMock.mock.lastCall?.[0]).toMatchObject({
      url: `${window.location.origin}/api/v1/auth/me`,
      credentials: 'include',
    });
  });

  it('returns null on 401', async () => {
    stubSession(null);
    await expect(loadSession()).resolves.toBeNull();
  });

  it('shares one request between parallel callers', async () => {
    const fetchMock = stubSession(null);
    await Promise.all([loadSession(), loadSession()]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
