import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import type { AvailableTime } from '../../appointments/api';
import {
  appointment,
  availabilityHandler,
  baseHandlers,
  BERGER,
  freezeTime,
  myAppointmentsHandler,
  time,
  YILMAZ,
} from '../../test/appointments';
import { renderRoute } from '../../test/render';
import { activeSession, apiError, stubSession } from '../../test/session';

// Friday 13 November, 14:00 and 14:15 Berlin time, and Monday 16 November, 08:00.
const FRIDAY_2PM = '2026-11-13T13:00:00Z';
const TIMES: AvailableTime[] = [
  time(BERGER, FRIDAY_2PM),
  time(YILMAZ, FRIDAY_2PM),
  time(BERGER, '2026-11-13T13:15:00Z'),
  time(BERGER, '2026-11-16T07:00:00Z'),
];

type Setup = {
  times?: AvailableTime[];
  book?: (request: Request) => Response | Promise<Response>;
  open?: number;
};

function setup(path = '/appointments/book', { times = TIMES, book, open = 0 }: Setup = {}) {
  const availability: URLSearchParams[] = [];
  const bookings: unknown[] = [];
  const list = availabilityHandler(times);
  stubSession(activeSession('PATIENT'), {
    ...baseHandlers,
    'GET /api/v1/availability': (request) => {
      availability.push(new URL(request.url).searchParams);
      return list(request);
    },
    'GET /api/v1/appointments/me': myAppointmentsHandler(() =>
      Array.from({ length: open }, (_, i) =>
        appointment({ id: `00000000-0000-4000-8000-00000000000${i}` }),
      ),
    ),
    'POST /api/v1/appointments': async (request) => {
      const body = await request.json();
      bookings.push(body);
      return book
        ? book(request)
        : Response.json(appointment({ startsAt: body.startsAt, reason: body.reason }), {
            status: 201,
          });
    },
  });
  const router = renderRoute(path);
  // Week requests ask for more than one result; the "next free time" lookup asks for one.
  const weekRequests = () => availability.filter((q) => q.get('limit') !== '1');
  return { router, bookings, availability, weekRequests };
}

const user = () => userEvent.setup();

async function openTime(name: string | RegExp) {
  await user().click(await screen.findByRole('button', { name }));
  return screen.findByRole('dialog');
}

describe('booking page', () => {
  beforeEach(() => freezeTime());

  it('shows the free times of the first free day of this week', async () => {
    const { weekRequests } = setup();

    expect(await screen.findByRole('heading', { level: 1, name: 'Termin buchen' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '9.–15. November 2026' })).toBeVisible();
    expect(
      screen.getByRole('radio', { name: /Freitag, 13. November \(heute\): 2 Uhrzeiten frei/ }),
    ).toBeChecked();
    expect(screen.getByRole('radio', { name: /Montag, 9. November/ })).toBeDisabled();
    expect(
      screen.getByRole('button', { name: '14:00 Uhr, 2 Ärztinnen oder Ärzte zur Auswahl' }),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: '14:15 Uhr, Dr. Anna Berger' })).toBeVisible();

    // Monday to Monday in practice time (CET = UTC+1), all doctors.
    const [week] = weekRequests();
    expect(week?.get('from')).toBe('2026-11-08T23:00:00.000Z');
    expect(week?.get('to')).toBe('2026-11-15T23:00:00.000Z');
    expect(week?.has('doctorId')).toBe(false);
  });

  it('books a time with the chosen doctor and reason', async () => {
    const { bookings } = setup();
    const dialog = await openTime('14:00 Uhr, 2 Ärztinnen oder Ärzte zur Auswahl');

    await user().click(within(dialog).getByRole('radio', { name: 'Dr. Mehmet Yilmaz' }));
    await user().click(within(dialog).getByRole('radio', { name: 'Impfung' }));
    await user().click(within(dialog).getByRole('button', { name: 'Termin verbindlich buchen' }));

    expect(await screen.findByRole('heading', { name: 'Ihr Termin ist gebucht' })).toBeVisible();
    expect(bookings).toEqual([
      { doctorId: YILMAZ.id, startsAt: '2026-11-13T13:00:00.000Z', reason: 'VACCINATION' },
    ]);
    expect(screen.getByRole('link', { name: 'Zu meinen Terminen' })).toHaveAttribute(
      'href',
      '/appointments',
    );
  });

  it('asks for a reason before sending anything', async () => {
    const { bookings } = setup();
    const dialog = await openTime('14:15 Uhr, Dr. Anna Berger');

    await user().click(within(dialog).getByRole('button', { name: 'Termin verbindlich buchen' }));

    expect(
      await within(dialog).findByText('Bitte wählen Sie den Grund Ihres Termins.'),
    ).toBeVisible();
    expect(within(dialog).getByRole('radiogroup', { name: 'Grund des Termins' })).toHaveAttribute(
      'aria-invalid',
      'true',
    );
    expect(bookings).toEqual([]);
  });

  it('reminds the patient to come fasting for a fasting blood test', async () => {
    setup();
    const dialog = await openTime('14:15 Uhr, Dr. Anna Berger');
    expect(within(dialog).queryByText(/Bitte kommen Sie nüchtern/)).not.toBeInTheDocument();

    await user().click(within(dialog).getByRole('radio', { name: 'Blutabnahme (nüchtern)' }));

    expect(within(dialog).getByText(/Bitte kommen Sie nüchtern/)).toBeVisible();
  });

  it('warns when a time is inside the online change deadline', async () => {
    setup();
    const dialog = await openTime('14:15 Uhr, Dr. Anna Berger');
    expect(within(dialog).getByText(/beginnt in weniger als 24 Stunden/)).toBeVisible();
  });

  it.each(['TIME_ALREADY_BOOKED', 'TIME_NOT_AVAILABLE'])(
    'reports a time taken meanwhile (%s) and reloads the free times',
    async (code) => {
      const { weekRequests } = setup('/appointments/book', { book: () => apiError(code, 409) });
      const dialog = await openTime('14:15 Uhr, Dr. Anna Berger');
      await user().click(within(dialog).getByRole('radio', { name: 'Rezept' }));
      const before = weekRequests().length;
      await user().click(within(dialog).getByRole('button', { name: 'Termin verbindlich buchen' }));

      expect(await within(dialog).findByRole('alert')).toHaveTextContent(
        /gerade vergeben|nicht mehr frei/,
      );
      expect(
        within(dialog).queryByRole('button', { name: 'Termin verbindlich buchen' }),
      ).toBeNull();
      await waitFor(() => expect(weekRequests().length).toBeGreaterThan(before));

      await user().click(within(dialog).getByRole('button', { name: 'Andere Uhrzeit wählen' }));
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    },
  );

  it('shows a generic text for other errors, never the server message', async () => {
    setup('/appointments/book', { book: () => apiError('APPOINTMENT_LIMIT_REACHED', 409) });
    const dialog = await openTime('14:15 Uhr, Dr. Anna Berger');
    await user().click(within(dialog).getByRole('radio', { name: 'Rezept' }));
    await user().click(within(dialog).getByRole('button', { name: 'Termin verbindlich buchen' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('bereits 5 offene Termine');
    expect(screen.queryByText('Server text.')).not.toBeInTheDocument();
  });

  it('offers the next free time as a shortcut', async () => {
    setup();
    await user().click(await screen.findByRole('button', { name: /Diesen Termin wählen/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('14:00 – 14:15 Uhr')).toBeVisible();
    expect(within(dialog).getByText('Dr. Anna Berger')).toBeVisible();
  });

  it('moves between weeks within the booking horizon', async () => {
    const { router, weekRequests } = setup();
    expect(await screen.findByRole('button', { name: 'Vorherige Woche' })).toBeDisabled();

    await user().click(screen.getByRole('button', { name: 'Nächste Woche' }));

    expect(await screen.findByRole('heading', { name: '16.–22. November 2026' })).toBeVisible();
    expect(router.state.location.search).toBe('?week=2026-11-16');
    expect(weekRequests().at(-1)?.get('from')).toBe('2026-11-15T23:00:00.000Z');
    expect(await screen.findByRole('button', { name: '08:00 Uhr, Dr. Anna Berger' })).toBeVisible();
  });

  it('filters by doctor', async () => {
    const { router, weekRequests } = setup();
    await user().click(await screen.findByRole('combobox', { name: 'Ärztin oder Arzt' }));
    await user().click(await screen.findByRole('option', { name: 'Dr. Mehmet Yilmaz' }));

    await waitFor(() => expect(router.state.location.search).toBe(`?doctor=${YILMAZ.id}`));
    await waitFor(() => expect(weekRequests().at(-1)?.get('doctorId')).toBe(YILMAZ.id));
    // Times of one doctor show no doctor name.
    expect(await screen.findByRole('button', { name: '14:00 Uhr' })).toBeVisible();
    expect(screen.queryByRole('button', { name: /14:15/ })).not.toBeInTheDocument();
  });

  it('ignores invalid query values', async () => {
    const { weekRequests } = setup('/appointments/book?week=2020-01-06&doctor=<script>');
    expect(await screen.findByRole('heading', { name: '9.–15. November 2026' })).toBeVisible();
    expect(weekRequests()[0]?.has('doctorId')).toBe(false);
  });

  it('points to the week of the next free time when a week is empty', async () => {
    setup('/appointments/book', { times: [time(BERGER, '2026-12-01T09:00:00Z')] });
    expect(await screen.findByText('In dieser Woche ist leider kein Termin frei.')).toBeVisible();

    await user().click(
      screen.getByRole('button', { name: 'Zur Woche mit dem nächsten freien Termin' }),
    );

    expect(
      await screen.findByRole('heading', { name: '30. November – 6. Dezember 2026' }),
    ).toBeVisible();
  });

  it('says so early when the open-appointment limit is reached', async () => {
    setup('/appointments/book', { open: 5 });
    expect(await screen.findByText(/bereits 5 offene Termine/)).toBeVisible();
  });

  it('renders names from the server as text', async () => {
    const evil = { id: BERGER.id, displayName: '<img src=x onerror=alert(1)>' };
    setup('/appointments/book', { times: [time(evil, FRIDAY_2PM)] });
    expect((await screen.findAllByText('<img src=x onerror=alert(1)>')).length).toBeGreaterThan(0);
    expect(document.querySelector('img')).toBeNull();
  });
});
