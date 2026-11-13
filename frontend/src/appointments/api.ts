import { api } from '../api/client';
import { ApiRequestError } from '../api/errors';
import type { components } from '../api/schema';

export type Appointment = components['schemas']['Appointment'];
export type AvailableTime = components['schemas']['AvailableTime'];
export type Doctor = components['schemas']['DoctorRef'];

const PAGE_SIZE = 100; // BR-20 maximum
const MAX_PAGES = 10; // bounds the work if a range is unexpectedly full
const MAX_RANGE_DAYS = 31; // BR-23
const HORIZON_DAYS = 365; // BR-23
const DAY_MS = 24 * 60 * 60 * 1000;

type Page<T> = { items: T[]; total: number };

async function allPages<T>(
  fetchPage: (offset: number) => Promise<{ data?: Page<T>; error?: unknown }>,
): Promise<T[]> {
  const items: T[] = [];
  for (let page = 0; page < MAX_PAGES; page++) {
    const { data, error } = await fetchPage(items.length);
    if (!data) throw new ApiRequestError(error);
    items.push(...data.items);
    if (data.items.length === 0 || items.length >= data.total) break;
  }
  return items;
}

/** Active doctors, sorted by name (A27). */
export function fetchDoctors(): Promise<Doctor[]> {
  return allPages((offset) =>
    api.GET('/api/v1/doctors', { params: { query: { limit: PAGE_SIZE, offset } } }),
  );
}

/** Every available time in `[from, to)` (at most 31 days, BR-23), ascending (A07). */
export function fetchAvailability(
  from: Date,
  to: Date,
  doctorId?: string,
): Promise<AvailableTime[]> {
  return allPages((offset) =>
    api.GET('/api/v1/availability', {
      params: {
        query: {
          from: from.toISOString(),
          to: to.toISOString(),
          doctorId,
          limit: PAGE_SIZE,
          offset,
        },
      },
    }),
  );
}

/**
 * The first available time from `from` on, or `null` if there is none within the booking horizon
 * of 365 days. Asks for one result per 31-day window, so it usually needs a single request.
 */
export async function findNextAvailable(
  from: Date,
  doctorId?: string,
): Promise<AvailableTime | null> {
  const horizon = from.getTime() + HORIZON_DAYS * DAY_MS;
  for (let start = from.getTime(); start < horizon; start += MAX_RANGE_DAYS * DAY_MS) {
    const end = Math.min(start + MAX_RANGE_DAYS * DAY_MS, horizon);
    const { data, error } = await api.GET('/api/v1/availability', {
      params: {
        query: {
          from: new Date(start).toISOString(),
          to: new Date(end).toISOString(),
          doctorId,
          limit: 1,
        },
      },
    });
    if (!data) throw new ApiRequestError(error);
    if (data.items[0]) return data.items[0];
  }
  return null;
}

type MyAppointmentsQuery = { status?: Appointment['status']; from?: Date; to?: Date };

/** The patient's own appointments (A11), ascending by start. */
export function fetchMyAppointments(query: MyAppointmentsQuery = {}): Promise<Appointment[]> {
  return allPages((offset) =>
    api.GET('/api/v1/appointments/me', {
      params: {
        query: {
          status: query.status,
          from: query.from?.toISOString(),
          to: query.to?.toISOString(),
          limit: PAGE_SIZE,
          offset,
        },
      },
    }),
  );
}

/** The patient's most recent appointments before `before`, newest first. */
export async function fetchRecentAppointments(before: Date, count = 20): Promise<Appointment[]> {
  const query = { to: before.toISOString(), limit: count };
  const first = await api.GET('/api/v1/appointments/me', { params: { query } });
  if (!first.data) throw new ApiRequestError(first.error);
  // The list is ascending, so the newest are on the last page.
  let page = first.data;
  if (page.total > count) {
    const last = await api.GET('/api/v1/appointments/me', {
      params: { query: { ...query, offset: Math.min(page.total - count, 10_000) } },
    });
    if (!last.data) throw new ApiRequestError(last.error);
    page = last.data;
  }
  return [...page.items].reverse();
}
