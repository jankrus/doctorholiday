import { vi } from 'vitest';
import type { Appointment, AvailableTime, Doctor } from '../appointments/api';
import type { PracticeSettings } from '../api/client';

/** Friday, 13 November 2026, 10:00 in Berlin. The week of 9-15 November is the first one. */
export const NOW = new Date('2026-11-13T09:00:00Z');

/** Fakes only `Date`, so timers (user-event, React Router) keep running. */
export function freezeTime(now: Date = NOW) {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(now);
}

export const BERGER: Doctor = {
  id: '00000000-0000-4000-8000-0000000000d1',
  displayName: 'Dr. Anna Berger',
};
export const YILMAZ: Doctor = {
  id: '00000000-0000-4000-8000-0000000000d2',
  displayName: 'Dr. Mehmet Yilmaz',
};

export const SETTINGS: PracticeSettings = {
  practiceName: 'Praxis am Park',
  cancellationDeadlineHours: 24,
  appointmentMinutes: 15,
  updatedAt: '2026-11-01T08:00:00Z',
};

export function time(doctor: Doctor, startsAt: string): AvailableTime {
  const end = new Date(new Date(startsAt).getTime() + 15 * 60_000).toISOString();
  return { doctor, startsAt: new Date(startsAt).toISOString(), endsAt: end };
}

export function appointment(overrides: Partial<Appointment> = {}): Appointment {
  const startsAt = overrides.startsAt ?? '2026-11-19T09:30:00.000Z';
  return {
    id: '00000000-0000-4000-8000-0000000000a1',
    status: 'BOOKED',
    reason: 'CHECKUP',
    doctor: BERGER,
    startsAt,
    endsAt: new Date(new Date(startsAt).getTime() + 15 * 60_000).toISOString(),
    bookedBy: 'PATIENT',
    createdAt: '2026-11-01T08:00:00Z',
    ...overrides,
  };
}

export const page = <T>(items: T[], request?: Request) => {
  const query = request ? new URL(request.url).searchParams : new URLSearchParams();
  const limit = Number(query.get('limit') ?? 20);
  const offset = Number(query.get('offset') ?? 0);
  return Response.json({
    items: items.slice(offset, offset + limit),
    limit,
    offset,
    total: items.length,
  });
};

/** Available times in the request's range (and of its doctor), like the backend filters them. */
export function availabilityHandler(times: AvailableTime[]) {
  return (request: Request) => {
    const query = new URL(request.url).searchParams;
    const from = query.get('from') ?? '';
    const to = query.get('to') ?? '';
    const doctorId = query.get('doctorId');
    return page(
      times.filter(
        (t) => t.startsAt >= from && t.startsAt < to && (!doctorId || t.doctor.id === doctorId),
      ),
      request,
    );
  };
}

/** Responses every patient page needs: settings and the doctors list. */
export const baseHandlers = {
  'GET /api/v1/settings': () => Response.json(SETTINGS),
  'GET /api/v1/doctors': (request: Request) => page([BERGER, YILMAZ], request),
};

/** `GET /appointments/me` with the status and time filters applied, ascending by start. */
export function myAppointmentsHandler(appointments: () => Appointment[]) {
  return (request: Request) => {
    const query = new URL(request.url).searchParams;
    const status = query.get('status');
    const from = query.get('from');
    const to = query.get('to');
    return page(
      appointments()
        .filter(
          (a) =>
            (!status || a.status === status) &&
            (!from || a.startsAt >= from) &&
            (!to || a.startsAt < to),
        )
        .sort((a, b) => a.startsAt.localeCompare(b.startsAt)),
      request,
    );
  };
}
