import { Theme } from '@radix-ui/themes';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { describe, expect, it } from 'vitest';
import { routes } from '../../routes';
import { apiError, stubSession } from '../../test/session';

function renderRegister(registerResponse: () => Response) {
  let sent: unknown;
  stubSession(null, {
    '/api/v1/auth/register': async (request) => {
      sent = await request.json();
      return registerResponse();
    },
  });
  const router = createMemoryRouter(routes, { initialEntries: ['/register'] });
  render(
    <Theme>
      <RouterProvider router={router} />
    </Theme>,
  );
  return { router, sent: () => sent };
}

type Input = { name?: string; email?: string; password?: string; confirm?: string };

async function fill({ name, email, password, confirm }: Input) {
  const user = userEvent.setup();
  await screen.findByRole('heading', { level: 1, name: 'Konto erstellen' });
  if (name) await user.type(screen.getByLabelText(/^Name/), name);
  if (email) await user.type(screen.getByLabelText('E-Mail-Adresse'), email);
  if (password) await user.type(screen.getByLabelText('Passwort'), password);
  if (confirm) await user.type(screen.getByLabelText('Passwort wiederholen'), confirm);
  return user;
}

async function submit(input: Input) {
  const user = await fill(input);
  await user.click(screen.getByRole('button', { name: 'Konto erstellen' }));
}

const valid = {
  name: 'Erika Mustermann',
  email: 'erika@example.test',
  password: 'correct horse battery',
  confirm: 'correct horse battery',
};

describe('register page', () => {
  it('registers and continues to the login page with a confirmation', async () => {
    const { router, sent } = renderRegister(() => new Response(null, { status: 202 }));
    await submit(valid);

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Vielen Dank für Ihre Registrierung.',
    );
    expect(router.state.location.pathname).toBe('/login');
    expect(sent()).toEqual({
      email: 'erika@example.test',
      password: 'correct horse battery',
      displayName: 'Erika Mustermann',
    });
  });

  it('leaves out an empty name', async () => {
    const { sent } = renderRegister(() => new Response(null, { status: 202 }));
    await submit({ ...valid, name: '' });

    await screen.findByRole('status');
    expect(sent()).toEqual({ email: 'erika@example.test', password: 'correct horse battery' });
  });

  it('shows field errors, focuses the first one and sends nothing', async () => {
    const { sent } = renderRegister(() => new Response(null, { status: 202 }));
    await submit({ email: 'not-an-email', password: 'short', confirm: 'other' });

    await screen.findByText('Bitte geben Sie eine gültige E-Mail-Adresse ein.');
    const email = screen.getByLabelText('E-Mail-Adresse');
    expect(email).toHaveAccessibleDescription('Bitte geben Sie eine gültige E-Mail-Adresse ein.');
    expect(email).toHaveAttribute('aria-invalid', 'true');
    expect(email).toHaveFocus();
    expect(screen.getByLabelText('Passwort')).toHaveAccessibleDescription(
      'Bitte verwenden Sie mindestens 12 Zeichen.',
    );
    expect(screen.getByLabelText('Passwort wiederholen')).toHaveAccessibleDescription(
      'Die Passwörter stimmen nicht überein.',
    );
    expect(sent()).toBeUndefined();
  });

  it('ticks off the password rules while typing', async () => {
    renderRegister(() => new Response(null, { status: 202 }));
    await fill({ password: 'short' });
    expect(screen.getByText('Mindestens 12 Zeichen')).not.toHaveAttribute('data-met');

    await fill({ password: ' but long enough', confirm: 'short but long enough' });
    expect(screen.getByText('Mindestens 12 Zeichen')).toHaveAttribute('data-met', 'true');
    expect(screen.getByText('Passwörter stimmen überein')).toHaveAttribute('data-met', 'true');
  });

  it('shows a generic error from the server', async () => {
    renderRegister(() => apiError('RATE_LIMITED', 429));
    await submit(valid);

    expect(await screen.findByRole('alert')).toHaveTextContent('Zu viele Versuche');
    expect(screen.queryByText('Server text.')).not.toBeInTheDocument();
  });
});
