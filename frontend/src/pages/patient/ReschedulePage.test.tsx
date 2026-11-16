import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
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

// Thursday 19 November, 10:30 Berlin, with Dr. Yilmaz; moved to Wednesday 18 November.
const CURRENT = appointment({ startsAt: '2026-11-19T09:30:00.000Z', doctor: YILMAZ });
const TIMES = [time(YILMAZ, '2026-11-18T13:00:00Z'), time(BERGER, '2026-11-18T13:00:00Z')];

function setup(id = CURRENT.id, reschedule?: () => Response) {
  const sent: unknown[] = [];
  const availability: URLSearchParams[] = [];
  const list = availabilityHandler(TIMES);
  stubSession(activeSession('PATIENT'), {
    ...baseHandlers,
    'GET /api/v1/appointments/me': myAppointmentsHandler(() => [CURRENT]),
    'GET /api/v1/availability': (request) => {
      availability.push(new URL(request.url).searchParams);
      return list(request);
    },
    [`POST /api/v1/appointments/${CURRENT.id}/reschedule`]: async (request) => {
      const body = await request.json();
      sent.push(body);
      return reschedule?.() ?? Response.json({ ...CURRENT, ...body, doctor: YILMAZ });
    },
  });
  const router = renderRoute(`/appointments/${id}/reschedule`);
  return { router, sent, availability };
}

describe('reschedule page', () => {
  beforeEach(() => freezeTime());

  it("starts with the appointment's doctor and week", async () => {
    const { availability } = setup();

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Termin verschieben' }),
    ).toBeVisible();
    expect(screen.getByText('Ihr aktueller Termin').nextElementSibling).toHaveTextContent(
      'Donnerstag, 19. November',
    );
    expect(screen.getByRole('heading', { name: '16.–22. November 2026' })).toBeVisible();
    expect(screen.getByRole('combobox', { name: 'Ärztin oder Arzt' })).toHaveTextContent(
      'Dr. Mehmet Yilmaz',
    );
    expect(availability.every((q) => q.get('doctorId') === YILMAZ.id)).toBe(true);
  });

  it('moves the appointment and confirms the new time', async () => {
    const { router, sent } = setup();
    await userEvent.click(await screen.findByRole('button', { name: '14:00 Uhr' }));
    const dialog = await screen.findByRole('dialog', { name: 'Termin verschieben' });

    expect(dialog).toHaveTextContent('Donnerstag, 19. November, 10:30 Uhr, Dr. Mehmet Yilmaz');
    expect(dialog).toHaveTextContent('Mittwoch, 18. November');
    expect(dialog).toHaveTextContent('Ihr bisheriger Termin bleibt bestehen');
    // No new reason: the appointment keeps its own (BR-22).
    expect(within(dialog).queryByRole('radiogroup', { name: 'Grund des Termins' })).toBeNull();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Termin verschieben' }));

    expect(
      await screen.findByRole('heading', { name: 'Ihr Termin wurde verschoben' }),
    ).toBeVisible();
    expect(sent).toEqual([{ startsAt: '2026-11-18T13:00:00.000Z', doctorId: YILMAZ.id }]);

    await userEvent.keyboard('{Escape}');
    expect(router.state.location.pathname).toBe('/appointments');
  });

  it('reports a time taken meanwhile', async () => {
    setup(CURRENT.id, () => apiError('TIME_ALREADY_BOOKED', 409));
    await userEvent.click(await screen.findByRole('button', { name: '14:00 Uhr' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Termin verschieben' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('gerade vergeben');
  });

  it('says so for an appointment that is not one of the open ones', async () => {
    setup('00000000-0000-4000-8000-0000000000ff');
    expect(
      await screen.findByText(/wurde nicht gefunden oder kann nicht mehr verschoben werden/),
    ).toBeVisible();
  });

  it('does not offer times inside the change deadline', async () => {
    freezeTime(new Date('2026-11-18T12:00:00Z'));
    setup();
    expect(await screen.findByText(/kann online nicht mehr\s+verschoben werden/)).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Nächste Woche' })).toBeNull();
  });
});
