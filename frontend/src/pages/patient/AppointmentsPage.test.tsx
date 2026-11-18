import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import type { Appointment } from '../../appointments/api';
import {
  appointment,
  availabilityHandler,
  BERGER,
  baseHandlers,
  freezeTime,
  myAppointmentsHandler,
  time,
  YILMAZ,
} from '../../test/appointments';
import { findToast, renderRoute } from '../../test/render';
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
  /** Delays the list reload after a cancellation, so the dialog is still open when it succeeds. */
  reloadDelayMs = 0,
) {
  let appointments = initial;
  const cancelled: string[] = [];
  const listHandler = myAppointmentsHandler(() => appointments);
  const session = activeSession('PATIENT');
  stubSession(
    { ...session, user: session.user && { ...session.user, displayName: 'Erika Mustermann' } },
    {
      ...baseHandlers,
      'GET /api/v1/availability': availabilityHandler([
        time(BERGER, '2026-11-16T07:00:00Z'),
        time(YILMAZ, '2026-11-16T08:00:00Z'),
      ]),
      'GET /api/v1/appointments/me': async (request) => {
        if (cancelled.length && reloadDelayMs) {
          await new Promise((resolve) => setTimeout(resolve, reloadDelayMs));
        }
        return listHandler(request);
      },
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
    },
  );
  renderRoute('/appointments');
  return { cancelled };
}

async function upcomingCards() {
  const section = await screen.findByRole('region', { name: 'Anstehende Termine' });
  return within(section).getAllByRole('listitem');
}

/** The upcoming appointment at `index`. */
async function historyItems() {
  const section = await screen.findByRole('region', { name: 'Verlauf' });
  return within(section).getAllByRole('listitem');
}

async function card(index: number) {
  const item = (await upcomingCards())[index];
  if (!item) throw new Error(`No upcoming appointment at ${index}`);
  return item;
}

describe('my appointments', () => {
  beforeEach(() => freezeTime());

  it('greets the patient by the time of day and names the next appointment', async () => {
    setup();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Guten Morgen, Erika Mustermann' }),
    ).toBeVisible();
    expect(
      screen.getByText('Ihr nächster Termin ist morgen um 09:00 Uhr bei Dr. Anna Berger.'),
    ).toBeVisible();
  });

  it('sums up open appointments, the next free time and the last visit', async () => {
    setup();
    const overview = await screen.findByRole('list', { name: 'Übersicht' });
    const [open, free, last] = within(overview).getAllByRole('listitem');

    expect(open).toHaveTextContent('2 von 5');
    expect(open).toHaveTextContent('Sie können noch 3 weitere buchen.');
    expect(free).toHaveTextContent('Montag, 16. November');
    expect(free).toHaveTextContent('08:00 Uhr · Dr. Anna Berger');
    expect(
      within(free as HTMLElement).getByRole('link', { name: 'Freie Termine ansehen' }),
    ).toHaveAttribute('href', '/appointments/book?week=2026-11-16');
    expect(last).toHaveTextContent('Montag, 2. November');
    expect(last).toHaveTextContent('Vorsorgeuntersuchung · Dr. Anna Berger');
    expect(last).toHaveTextContent('Vor 11 Tagen');
  });

  it('lists upcoming appointments with their details and change deadline', async () => {
    setup();
    const [first, second] = await upcomingCards();

    expect(first).toHaveTextContent('Nächster Termin');
    expect(first).toHaveTextContent('Morgen');
    expect(first).toHaveTextContent('Samstag, 14. November');
    expect(first).toHaveTextContent('09:00 – 09:15 Uhr');
    expect(second).toHaveTextContent('Donnerstag, 19. November');
    expect(second).toHaveTextContent('Dr. Mehmet Yilmaz');
    expect(second).toHaveTextContent('Blutabnahme (nüchtern)');
    expect(second).toHaveTextContent('Nüchtern erscheinen');
    expect(second).toHaveTextContent('In 6 Tagen');
    expect(second).toHaveTextContent('Änderbar bis Mittwoch, 18. November, 10:30 Uhr');
    expect(screen.getByText(/online bis 24 Stunden vor Beginn/)).toBeVisible();
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

  it('shows past and cancelled appointments in the history, newest first', async () => {
    setup();
    const items = await historyItems();

    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('Freitag, 20. November');
    expect(items[0]).toHaveTextContent('Von der Praxis abgesagt');
    expect(items[1]).toHaveTextContent('Montag, 2. November');
    expect(items[1]).toHaveTextContent('09:00 – 09:15 Uhr · Dr. Anna Berger');
    expect(items[1]).toHaveTextContent('Vorsorgeuntersuchung');
  });

  it('shortens a long history until the patient asks for all of it', async () => {
    const past = Array.from({ length: 6 }, (_, index) =>
      appointment({
        id: `00000000-0000-4000-8000-0000000000b${index}`,
        startsAt: `2026-10-0${index + 1}T08:00:00.000Z`,
      }),
    );
    setup(past);
    expect(await historyItems()).toHaveLength(4);

    await userEvent.click(screen.getByRole('button', { name: 'Alle 6 anzeigen' }));
    expect(await historyItems()).toHaveLength(6);
    expect(screen.getByRole('button', { name: 'Weniger anzeigen' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('cancels after confirmation and moves the appointment to the history', async () => {
    const { cancelled } = setup();
    await userEvent.click(within(await card(1)).getByRole('button', { name: 'Absagen' }));

    const dialog = await screen.findByRole('alertdialog', { name: 'Termin absagen?' });
    expect(dialog).toHaveTextContent('Donnerstag, 19. November, 10:30 Uhr bei Dr. Mehmet Yilmaz');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Termin absagen' }));

    expect(await findToast()).toHaveTextContent(
      'Ihr Termin am Donnerstag, 19. November, 10:30 Uhr wurde abgesagt.',
    );
    expect(screen.getByRole('heading', { name: 'Anstehende Termine' })).toHaveFocus();
    expect(cancelled).toEqual([NEXT_WEEK.id]);
    expect(await upcomingCards()).toHaveLength(1);
    expect(await historyItems()).toHaveLength(3);
  });

  it('confirms the cancellation even while the list still reloads behind the dialog', async () => {
    // The toast is raised while the dialog is still open, which hides the toast viewport from
    // assistive technology until it closes; the live announcement is read out anyway.
    setup(undefined, undefined, 300);
    await userEvent.click(within(await card(1)).getByRole('button', { name: 'Absagen' }));
    const dialog = await screen.findByRole('alertdialog', { name: 'Termin absagen?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Termin absagen' }));

    await waitFor(() =>
      expect(
        screen.getAllByRole('status').some((el) => el.textContent?.includes('wurde abgesagt')),
      ).toBe(true),
    );
    expect(await findToast()).toHaveTextContent('wurde abgesagt');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Anstehende Termine' })).toHaveFocus(),
    );
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
    expect(screen.getByText('Sie haben derzeit keine anstehenden Termine.')).toBeVisible();
    expect(screen.getByText('Noch keiner')).toBeVisible();
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
