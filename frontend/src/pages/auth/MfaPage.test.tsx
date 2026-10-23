import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderRoute } from '../../test/render';
import { activeSession, apiError, patientWithOffer, stubSession } from '../../test/session';

const RECOVERY_CODES = [
  'k7m2p-q4x5z',
  'abcde-fghij',
  'mnopq-rstuv',
  'wxyz2-34567',
  'qwert-zuiop',
  'asdfg-hjklm',
  'yxcvb-nmqwe',
  'pomnb-vcxyl',
  'kjhgf-dsaqw',
  'zt5r4-e3w2q',
];

/** App codes go into the digit boxes (focus moves on by itself), recovery codes into one field. */
async function typeCode(label: string, code: string) {
  const user = userEvent.setup();
  if (label === 'Bestätigungscode') {
    await user.click(await screen.findByLabelText('Ziffer 1 von 6'));
    await user.keyboard(code);
  } else {
    await user.type(await screen.findByLabelText(label), code);
  }
  return user;
}

const codeBoxes = () => screen.getAllByLabelText(/^Ziffer \d von 6$/);

describe('MFA login challenge', () => {
  function renderChallenge(verify: (body: unknown) => Response) {
    const sent: unknown[] = [];
    const fetchMock = stubSession(
      { state: 'MFA_PENDING' },
      {
        '/api/v1/auth/mfa/verify': async (request, setSession) => {
          const body = await request.json();
          sent.push(body);
          const response = verify(body);
          if (response.ok) setSession((await response.clone().json()).session);
          return response;
        },
      },
    );
    return { router: renderRoute('/mfa'), sent, fetchMock };
  }

  it('accepts the app code, also with a space, and opens the start page', async () => {
    const { router, sent } = renderChallenge(() =>
      Response.json({ session: activeSession('DOCTOR') }),
    );
    const user = await typeCode('Bestätigungscode', '123 456');
    await user.click(screen.getByRole('button', { name: 'Bestätigen' }));

    expect(await screen.findByRole('heading', { name: 'Praxis' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/staff');
    expect(sent).toEqual([{ code: '123456' }]);
  });

  it('checks the format before sending', async () => {
    const { sent } = renderChallenge(() => Response.json({ session: activeSession('DOCTOR') }));
    const user = await typeCode('Bestätigungscode', '12ab');
    await user.click(screen.getByRole('button', { name: 'Bestätigen' }));

    await screen.findByText('Bitte geben Sie den 6-stelligen Code aus Ihrer App ein.');
    expect(screen.getByRole('group', { name: 'Bestätigungscode' })).toHaveAccessibleDescription(
      'Bitte geben Sie den 6-stelligen Code aus Ihrer App ein.',
    );
    expect(sent).toEqual([]);
  });

  it('shows a generic error for a wrong code and clears the field', async () => {
    renderChallenge(() => apiError('INVALID_MFA_CODE', 400));
    const user = await typeCode('Bestätigungscode', '654321');
    await user.click(screen.getByRole('button', { name: 'Bestätigen' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Der Code ist ungültig');
    expect(screen.queryByText('Server text.')).not.toBeInTheDocument();
    for (const box of codeBoxes()) expect(box).toHaveValue('');
    expect(screen.getByLabelText('Ziffer 1 von 6')).toHaveFocus();
  });

  it('accepts a recovery code instead', async () => {
    const { sent } = renderChallenge(() => Response.json({ session: activeSession('DOCTOR') }));
    await userEvent.click(
      await screen.findByRole('button', { name: /Wiederherstellungscode verwenden/ }),
    );
    const user = await typeCode('Wiederherstellungscode', ' ABCDE-FGHIJ ');
    await user.click(screen.getByRole('button', { name: 'Bestätigen' }));

    await screen.findByRole('heading', { name: 'Praxis' });
    expect(sent).toEqual([{ recoveryCode: 'abcde-fghij' }]);
  });
});

describe('MFA enrolment', () => {
  function renderEnrolment(confirm: () => Response) {
    const fetchMock = stubSession(
      { state: 'MFA_ENROLLMENT_REQUIRED' },
      {
        '/api/v1/auth/mfa/enroll': () =>
          Response.json({
            secret: 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',
            otpauthUri:
              'otpauth://totp/Doctor%20Holiday:admin%40example.test?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=Doctor%20Holiday',
          }),
        '/api/v1/auth/mfa/verify': async (_, setSession) => {
          const response = confirm();
          if (response.ok) setSession((await response.clone().json()).session);
          return response;
        },
      },
    );
    return { router: renderRoute('/mfa'), fetchMock };
  }

  const confirmed = () =>
    Response.json({
      session: { ...activeSession('ADMIN'), setupRequired: true },
      recoveryCodes: RECOVERY_CODES,
    });

  async function startAndConfirm(code = '123456') {
    await userEvent.click(await screen.findByRole('button', { name: 'Einrichtung starten' }));
    const user = await typeCode('Bestätigungscode', code);
    await user.click(screen.getByRole('button', { name: 'Bestätigen und aktivieren' }));
  }

  it('shows the QR code and the key for manual entry', async () => {
    renderEnrolment(confirmed);
    await userEvent.click(await screen.findByRole('button', { name: 'Einrichtung starten' }));

    expect(
      await screen.findByRole('img', { name: 'QR-Code für die Authenticator-App' }),
    ).toBeInTheDocument();
    expect(screen.getByText('JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP')).toBeInTheDocument();
  });

  it('shows the recovery codes once and continues only after confirming they are saved', async () => {
    const { router, fetchMock } = renderEnrolment(confirmed);
    await startAndConfirm();

    const list = await screen.findByRole('list', { name: 'Wiederherstellungscodes' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(10);
    for (const code of RECOVERY_CODES) expect(within(list).getByText(code)).toBeInTheDocument();

    const next = screen.getByRole('button', { name: 'Weiter' });
    expect(next).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(next);

    expect(await screen.findByRole('heading', { name: 'Praxis einrichten' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/setup');

    // Acceptance criteria of #24: nothing in browser storage, no request to a third party.
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    for (const [request] of fetchMock.mock.calls) {
      expect(new URL(request.url).origin).toBe(window.location.origin);
    }
  });

  it('keeps the QR code after a wrong code', async () => {
    renderEnrolment(() => apiError('INVALID_MFA_CODE', 400));
    await startAndConfirm('999999');

    expect(await screen.findByRole('alert')).toHaveTextContent('Der Code ist ungültig');
    expect(screen.getByRole('img', { name: /QR-Code/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText('Ziffer 1 von 6')).toHaveFocus());
    for (const box of codeBoxes()) expect(box).toHaveValue('');
  });
});

describe('optional MFA offer for patients', () => {
  function renderOffer() {
    let declined = false;
    const fetchMock = stubSession(patientWithOffer(), {
      'POST /api/v1/auth/mfa/decline': (_, setSession) => {
        declined = true;
        setSession(activeSession('PATIENT'));
        return new Response(null, { status: 204 });
      },
      'POST /api/v1/auth/mfa/enroll': () =>
        Response.json({
          secret: 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',
          otpauthUri:
            'otpauth://totp/Doctor%20Holiday:patient?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',
        }),
      'POST /api/v1/auth/mfa/verify': (_, setSession) => {
        const session = activeSession('PATIENT');
        setSession(session);
        return Response.json({ session, recoveryCodes: RECOVERY_CODES });
      },
    });
    return { router: renderRoute('/appointments'), declined: () => declined, fetchMock };
  }

  it('is shown after login instead of the start page', async () => {
    const { router } = renderOffer();
    expect(
      await screen.findByRole('heading', { name: 'Konto zusätzlich schützen?' }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/mfa');
    expect(screen.queryByRole('button', { name: /abmelden/ })).not.toBeInTheDocument();
  });

  it('can be declined once and then opens the appointments', async () => {
    const { router, declined } = renderOffer();
    await userEvent.click(
      await screen.findByRole('button', { name: 'Ohne zweiten Faktor fortfahren' }),
    );

    expect(await screen.findByRole('heading', { name: 'Meine Termine' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/appointments');
    expect(declined()).toBe(true);
  });

  it('can be accepted and ends with the recovery codes', async () => {
    const { router } = renderOffer();
    await userEvent.click(await screen.findByRole('button', { name: 'Zweiten Faktor einrichten' }));
    const user = await typeCode('Bestätigungscode', '123456');
    await user.click(screen.getByRole('button', { name: 'Bestätigen und aktivieren' }));
    await screen.findByRole('list', { name: 'Wiederherstellungscodes' });
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: 'Weiter' }));

    expect(await screen.findByRole('heading', { name: 'Meine Termine' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/appointments');
  });
});

describe('mandatory MFA enrolment for practice roles', () => {
  it('offers no way to skip, only to log out', async () => {
    stubSession({ state: 'MFA_ENROLLMENT_REQUIRED' });
    renderRoute('/mfa');
    expect(
      await screen.findByRole('button', { name: 'Abbrechen und abmelden' }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Ohne zweiten Faktor/ })).not.toBeInTheDocument();
  });
});

describe('logout', () => {
  it('ends the session and shows the login page', async () => {
    let loggedOut = false;
    stubSession(
      { state: 'MFA_PENDING' },
      {
        'POST /api/v1/auth/logout': (_, setSession) => {
          loggedOut = true;
          setSession(null);
          return new Response(null, { status: 204 });
        },
      },
    );
    const router = renderRoute('/mfa');
    await userEvent.click(await screen.findByRole('button', { name: 'Abbrechen und abmelden' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Sie wurden abgemeldet.');
    expect(router.state.location.pathname).toBe('/login');
    expect(loggedOut).toBe(true);
  });
});
