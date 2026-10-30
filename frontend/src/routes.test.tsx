import { Theme } from '@radix-ui/themes';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { describe, expect, it } from 'vitest';
import type { SessionInfo } from './api/client';
import { routes } from './routes';
import { activeSession, stubSession } from './test/session';

function renderAt(path: string, session: SessionInfo | null) {
  stubSession(session);
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <Theme>
      <RouterProvider router={router} />
    </Theme>,
  );
  return router;
}

async function expectPage(router: ReturnType<typeof renderAt>, path: string, heading: string) {
  expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe(path);
}

describe('routing', () => {
  it.each(['/', '/appointments', '/staff', '/admin', '/mfa', '/setup'])(
    'redirects %s to /login without a session',
    async (path) => {
      await expectPage(renderAt(path, null), '/login', 'Log in');
    },
  );

  it('keeps users on pages for their role', async () => {
    await expectPage(renderAt('/staff', activeSession('DOCTOR')), '/staff', 'Practice');
  });

  it('redirects users away from pages of other roles', async () => {
    await expectPage(
      renderAt('/admin', activeSession('PATIENT')),
      '/appointments',
      'My appointments',
    );
  });

  it('redirects to /mfa until MFA is verified', async () => {
    await expectPage(
      renderAt('/admin', { state: 'MFA_PENDING' }),
      '/mfa',
      'Two-factor authentication',
    );
  });

  it('redirects an admin to /setup until the practice settings are saved', async () => {
    await expectPage(
      renderAt('/admin', { ...activeSession('ADMIN'), setupRequired: true }),
      '/setup',
      'Practice setup',
    );
  });

  it('sends an admin away from /setup once it is done', async () => {
    await expectPage(renderAt('/setup', activeSession('ADMIN')), '/admin', 'Administration');
  });

  it('sends logged-in users from /login to their start page', async () => {
    await expectPage(renderAt('/login', activeSession('ADMIN')), '/admin', 'Administration');
  });

  it('shows a generic error when the session lookup fails', async () => {
    stubSession(null).mockResolvedValue(new Response('upstream detail', { status: 502 }));
    const router = createMemoryRouter(routes, { initialEntries: ['/appointments'] });
    render(<RouterProvider router={router} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong');
    expect(screen.queryByText('upstream detail')).not.toBeInTheDocument();
  });

  it('shows a not-found page for unknown paths', async () => {
    renderAt('/does-not-exist', null);
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  });
});
