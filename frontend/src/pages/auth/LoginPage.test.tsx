import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { findToast, queryToasts, renderRoute } from '../../test/render';
import { activeSession, apiError, stubSession } from '../../test/session';

function renderLogin(loginResponse: () => Response | Promise<Response>) {
  let sent: unknown;
  const fetchMock = stubSession(null, {
    '/api/v1/auth/login': async (request) => {
      sent = await request.json();
      // From now on the backend knows the session.
      const response = await loginResponse();
      if (response.ok) {
        const session = await response.clone().json();
        fetchMock.mockImplementation(async (r: Request) =>
          new URL(r.url).pathname === '/api/v1/auth/me' ? Response.json(session) : response,
        );
      }
      return response;
    },
  });
  return { router: renderRoute('/login'), sent: () => sent };
}

async function submit(email: string, password: string) {
  const user = userEvent.setup();
  await screen.findByRole('heading', { level: 1, name: 'Anmelden' });
  if (email) await user.type(screen.getByLabelText('E-Mail-Adresse'), email);
  if (password) await user.type(screen.getByLabelText('Passwort'), password);
  await user.click(screen.getByRole('button', { name: 'Anmelden' }));
}

describe('login page', () => {
  it('sends the credentials and opens the start page of the role', async () => {
    const { router, sent } = renderLogin(() => Response.json(activeSession('PATIENT')));
    await submit('patient@example.test', 'correct horse battery');

    expect(await screen.findByRole('heading', { name: 'Meine Termine' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/appointments');
    expect(sent()).toEqual({ email: 'patient@example.test', password: 'correct horse battery' });
  });

  it('continues to the MFA step when the session still needs a code', async () => {
    const { router } = renderLogin(() => Response.json({ state: 'MFA_PENDING' }));
    await submit('doctor@example.test', 'correct horse battery');

    expect(
      await screen.findByRole('heading', { name: 'Anmeldung bestätigen' }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/mfa');
  });

  it('shows a generic error, keeps the e-mail and clears the password', async () => {
    renderLogin(() => apiError('INVALID_CREDENTIALS', 401));
    await submit('patient@example.test', 'wrong password');

    expect(await findToast()).toHaveTextContent('E-Mail-Adresse oder Passwort ist falsch.');
    expect(screen.queryByText('Server text.')).not.toBeInTheDocument();
    expect(screen.getByLabelText('E-Mail-Adresse')).toHaveValue('patient@example.test');
    expect(screen.getByLabelText('Passwort')).toHaveValue('');
    expect(screen.getByLabelText('Passwort')).toHaveFocus();
  });

  it('tells the user to wait after too many attempts', async () => {
    renderLogin(() => apiError('RATE_LIMITED', 429));
    await submit('patient@example.test', 'wrong password');

    expect(await findToast()).toHaveTextContent('Zu viele Versuche');
  });

  it('shows a generic error when the network fails', async () => {
    renderLogin(() => Promise.reject(new TypeError('Failed to fetch')));
    await submit('patient@example.test', 'correct horse battery');

    expect(await findToast()).toHaveTextContent('Etwas ist schiefgelaufen');
  });

  it('asks for both fields without calling the API', async () => {
    const { sent } = renderLogin(() => Response.json(activeSession('PATIENT')));
    await submit('', '');

    expect(await findToast()).toHaveTextContent(
      'Bitte geben Sie Ihre E-Mail-Adresse und Ihr Passwort ein.',
    );
    expect(sent()).toBeUndefined();
  });

  it('replaces the error of the last attempt instead of stacking it', async () => {
    let attempts = 0;
    renderLogin(() => {
      attempts += 1;
      return attempts === 1 ? apiError('INVALID_CREDENTIALS', 401) : apiError('RATE_LIMITED', 429);
    });
    await submit('patient@example.test', 'wrong password');
    expect(await findToast()).toHaveTextContent('E-Mail-Adresse oder Passwort ist falsch.');

    await userEvent.type(screen.getByLabelText('Passwort'), 'wrong again');
    await userEvent.click(screen.getByRole('button', { name: 'Anmelden' }));

    expect(await findToast()).toHaveTextContent('Zu viele Versuche');
    expect(queryToasts()).toHaveLength(1);
  });

  it('closes the error once a new attempt succeeds', async () => {
    let attempts = 0;
    renderLogin(() => {
      attempts += 1;
      return attempts === 1
        ? apiError('INVALID_CREDENTIALS', 401)
        : Response.json(activeSession('PATIENT'));
    });
    await submit('patient@example.test', 'wrong password');
    await findToast();

    await userEvent.type(screen.getByLabelText('Passwort'), 'correct horse battery');
    await userEvent.click(screen.getByRole('button', { name: 'Anmelden' }));

    expect(await screen.findByRole('heading', { name: 'Meine Termine' })).toBeInTheDocument();
    expect(queryToasts()).toHaveLength(0);
  });

  it('can show the password', async () => {
    renderLogin(() => Response.json(activeSession('PATIENT')));
    const password = await screen.findByLabelText('Passwort');
    const toggle = screen.getByRole('button', { name: 'Passwort anzeigen' });

    expect(password).toHaveAttribute('type', 'password');
    await userEvent.click(toggle);
    expect(password).toHaveAttribute('type', 'text');
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
  });
});
