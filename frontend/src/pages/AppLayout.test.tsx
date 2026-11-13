import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { baseHandlers } from '../test/appointments';
import { renderRoute } from '../test/render';
import { activeSession, stubSession } from '../test/session';

describe('app layout', () => {
  it('shows the practice, the account and the patient navigation', async () => {
    const session = activeSession('PATIENT');
    stubSession(
      { ...session, user: session.user && { ...session.user, displayName: 'Erika Mustermann' } },
      baseHandlers,
    );
    renderRoute('/appointments');

    const nav = await screen.findByRole('navigation', { name: 'Hauptnavigation' });
    // Radix repeats each label in a `visibility: hidden` span; jsdom has no CSS, so it counts twice.
    expect(within(nav).getByRole('link', { name: /^Meine Termine/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(nav).getByRole('link', { name: /^Termin buchen/ })).toHaveAttribute(
      'href',
      '/appointments/book',
    );
    expect(await screen.findByText('Praxis am Park')).toBeInTheDocument();
    expect(screen.getByText('Erika Mustermann')).toBeInTheDocument();
  });

  it('has no tab navigation for roles with a single area', async () => {
    stubSession(activeSession('ADMIN'), baseHandlers);
    renderRoute('/admin');
    expect(await screen.findByRole('heading', { name: 'Verwaltung' })).toBeVisible();
    expect(screen.queryByRole('navigation', { name: 'Hauptnavigation' })).toBeNull();
  });
});
