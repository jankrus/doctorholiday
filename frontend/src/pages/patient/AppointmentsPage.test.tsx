import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import type { Appointment } from '../../appointments/api';
import {
  appointment,
  baseHandlers,
  freezeTime,
  myAppointmentsHandler,
  YILMAZ,
} from '../../test/appointments';
import { renderRoute } from '../../test/render';
import { activeSession, apiError, stubSession } from '../../test/session';

// Now: Friday 13 November 2026, 10:00 Berlin. The deadline is 24 hours.
const TOMORROW = appointment({
  id: '00000000-0000-4000-8000-0000000000a1',
  startsAt: '2026-11-14T08:00:00.000Z',
});
const NEXT_WEEK = appointment({
  id: '00000000-0000-4000-8000-0000000000a2',
  startsAt: '2026-11-19T09:30:00.000Z',
  doctor: YILMAZ,
  reason: 'BLOOD_TEST_FASTING',
});
const PAST = appointment({
  id: '00000000-0000-4000-8000-0000000000a3',
  startsAt: '2026-11-02T08:00:00.000Z',
});
const CANCELLED = appointment({
  id: '00000000-0000-4000-8000-0000000000a4',
  startsAt: '2026-11-20T08:00:00.000Z',
  status: 'CANCELLED',
  cancelledBy: 'PRACTICE',
});

function setup(
  initial: Appointment[] = [TOMORROW, NEXT_WEEK, PAST, CANCELLED],
  cancel?: () => Response,
) {
  let appointments = initial;
  const cancelled: string[] = [];
  stubSession(activeSession('PATIENT'), {
    ...baseHandlers,
    'GET /api/v1/appointments/me': myAppointmentsHandler(() => appointments),
    [`POST /api/v1/appointments/${NEXT_WEEK.id}/cancel`]: () => {
      cancelled.push(NEXT_WEEK.id);
      if (cancel) return cancel();
      const result = {
        ...NEXT_WEEK,
        status: 'CANCELLED' as const,
        cancelledBy: 'PATIENT' as const,
      };
      appointments = appointments.map((a) => (a.id === NEXT_WEEK.id ? result : a));
      return Response.json(result);
    },
  });
  renderRoute('/appointments');
  return { cancelled };
}

async function upcomingCards() {
  const section = await screen.findByRole('region', { name: 'Anstehende Termine' });
  return within(section).getAllByRole('listitem');
}

/** The upcoming appointment at `index`. */
async function card(index: number) {
  const item = (await upcomingCards())[index];
  if (!item) throw new Error(`No upcoming appointment at ${index}`);
  return item;
}

describe('my appointments', () => {
  beforeEach(() => freezeTime());

  it('lists upcoming appointments with their details and change deadline', async () => {
    setup();
    const [first, second] = await upcomingCards();

    expect(first).toHaveTextContent('Nächster Termin');
    expect(first).toHaveTextContent('Samstag, 14. November');
    expect(first).toHaveTextContent('09:00 – 09:15 Uhr');
    expect(second).toHaveTextContent('Donnerstag, 19. November');
    expect(second).toHaveTextContent('Dr. Mehmet Yilmaz');
    expect(second).toHaveTextContent('Blutabnahme (nüchtern)');
    expect(second).toHaveTextContent('Nüchtern erscheinen');
    expect(second).toHaveTextContent('Änderbar bis Mittwoch, 18. November, 10:30 Uhr');
    expect(screen.getByText(/Bis 24 Stunden vor Beginn/)).toBeVisible();
  });

  it('offers no online changes inside the deadline', async () => {
    setup();
    const first = await card(0);
    const second = await card(1);

    expect(first).toHaveTextContent('Online nicht mehr änderbar');
    expect(within(first).queryByRole('button', { name: 'Absagen' })).toBeNull();
    expect(within(first).queryByRole('link', { name: 'Verschieben' })).toBeNull();
    expect(within(second).getByRole('link', { name: 'Verschieben' })).toHaveAttribute(
      'href',
      `/appointments/${NEXT_WEEK.id}/reschedule`,
    );
  });

  it('keeps past and cancelled appointments in a separate history', async () => {
    setup();
    await upcomingCards();
    const history = screen.getByText('Vergangene und abgesagte Termine (2)');
    await userEvent.click(history);

    const details = history.closest('details');
    if (!details) throw new Error('No history section');
    const items = within(details).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Freitag, 20. November');
    expect(items[0]).toHaveTextContent('Von der Praxis abgesagt');
    expect(items[1]).toHaveTextContent('Montag, 2. November');
  });

  it('cancels after confirmation and moves the appointment to the history', async () => {
    const { cancelled } = setup();
    await userEvent.click(within(await card(1)).getByRole('button', { name: 'Absagen' }));

    const dialog = await screen.findByRole('alertdialog', { name: 'Termin absagen?' });
    expect(dialog).toHaveTextContent('Donnerstag, 19. November, 10:30 Uhr bei Dr. Mehmet Yilmaz');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Termin absagen' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Ihr Termin am Donnerstag, 19. November, 10:30 Uhr wurde abgesagt.',
    );
    expect(cancelled).toEqual([NEXT_WEEK.id]);
    expect(await upcomingCards()).toHaveLength(1);
    expect(screen.getByText('Vergangene und abgesagte Termine (3)')).toBeVisible();
  });

  it('keeps the appointment when the patient changes their mind', async () => {
    const { cancelled } = setup();
    await userEvent.click(within(await card(1)).getByRole('button', { name: 'Absagen' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Termin behalten' }));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(cancelled).toEqual([]);
  });

  it('explains a deadline that passed while the page was open', async () => {
    setup(undefined, () => apiError('CANCELLATION_DEADLINE_PASSED', 409));
    await userEvent.click(within(await card(1)).getByRole('button', { name: 'Absagen' }));
    const dialog = await screen.findByRole('alertdialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Termin absagen' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'Für eine Online-Änderung ist es jetzt zu spät.',
    );
  });

  it('invites to book when nothing is planned', async () => {
    setup([]);
    expect(await screen.findByText('Sie haben keine anstehenden Termine.')).toBeVisible();
    expect(screen.getAllByRole('link', { name: 'Termin buchen' }).at(-1)).toHaveAttribute(
      'href',
      '/appointments/book',
    );
  });

  it('shows a generic error when the list cannot be loaded', async () => {
    stubSession(activeSession('PATIENT'), {
      ...baseHandlers,
      'GET /api/v1/appointments/me': () => apiError('INTERNAL_ERROR', 500),
    });
    renderRoute('/appointments');
    expect(await screen.findByRole('alert')).toHaveTextContent('Etwas ist schiefgelaufen');
  });
});
