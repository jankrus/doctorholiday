import { errorMessage } from '../api/errors';
import {
  fetchAvailability,
  fetchDoctors,
  findNextAvailable,
  type AvailableTime,
  type Doctor,
} from './api';
import { addDays, dateKey, isDateKey, mondayOf, startOfDay } from './time';

/** `doctor` query value that shows every doctor. */
export const ALL_DOCTORS = 'all';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type BrowserData = {
  doctors: Doctor[];
  /** A doctor's ID or `ALL_DOCTORS`. */
  doctor: string;
  /** Monday of the shown week (date key in the practice time zone). */
  week: string;
  firstWeek: string;
  lastWeek: string;
  today: string;
  times: AvailableTime[];
  /** First available time from now on, for the "next free time" shortcut. */
  next: AvailableTime | null;
  error?: string;
};

/**
 * Data for the availability browser. The week and the doctor filter live in the query string
 * (`?week=YYYY-MM-DD&doctor=<id>|all`), so the back button and a reload keep the view; neither is
 * personal data. Invalid values fall back to the defaults.
 */
export async function loadAvailability(
  url: URL,
  defaults: { doctor?: string; week?: string } = {},
): Promise<BrowserData> {
  const now = new Date();
  const today = dateKey(now);
  const firstWeek = mondayOf(today);
  // BR-23: nothing is offered more than 365 days ahead.
  const lastWeek = mondayOf(addDays(today, 365));

  const weekParam = url.searchParams.get('week') ?? defaults.week ?? '';
  let week = isDateKey(weekParam) ? mondayOf(weekParam) : firstWeek;
  if (week < firstWeek) week = firstWeek;
  if (week > lastWeek) week = lastWeek;

  const base = { doctors: [], doctor: ALL_DOCTORS, week, firstWeek, lastWeek, today };

  let doctors: Doctor[];
  try {
    doctors = await fetchDoctors();
  } catch (error) {
    return { ...base, times: [], next: null, error: errorMessage(error) };
  }

  const doctorParam = url.searchParams.get('doctor') ?? defaults.doctor ?? ALL_DOCTORS;
  const doctor =
    UUID.test(doctorParam) && doctors.some(({ id }) => id === doctorParam)
      ? doctorParam
      : ALL_DOCTORS;
  const doctorId = doctor === ALL_DOCTORS ? undefined : doctor;

  try {
    const [times, next] = await Promise.all([
      fetchAvailability(startOfDay(week), startOfDay(addDays(week, 7)), doctorId),
      findNextAvailable(now, doctorId),
    ]);
    return { ...base, doctors, doctor, times, next };
  } catch (error) {
    return { ...base, doctors, doctor, times: [], next: null, error: errorMessage(error) };
  }
}
