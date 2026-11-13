// Dates and times in the practice time zone. Working hours and availability are defined in
// Europe/Berlin (BR-08, BR-23), so every date and time is shown there, wherever the browser is.
// The API speaks UTC timestamps; a "date key" (`YYYY-MM-DD`) names a calendar day in the practice.

export const PRACTICE_TIME_ZONE = 'Europe/Berlin';
const LOCALE = 'de-DE';
const DAY_MS = 24 * 60 * 60 * 1000;

const partsFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: PRACTICE_TIME_ZONE,
  year: 'numeric',
  month: 'numeric',
  day: 'numeric',
  hour: 'numeric',
  minute: 'numeric',
  second: 'numeric',
  hourCycle: 'h23',
});

type ZonedParts = { year: number; month: number; day: number; hour: number; minute: number };

function zonedParts(date: Date): ZonedParts & { second: number } {
  const parts: Record<string, number> = {};
  for (const { type, value } of partsFormat.formatToParts(date)) {
    if (type !== 'literal') parts[type] = Number(value);
  }
  return {
    year: parts.year ?? 0,
    month: parts.month ?? 0,
    day: parts.day ?? 0,
    hour: parts.hour ?? 0,
    minute: parts.minute ?? 0,
    second: parts.second ?? 0,
  };
}

const pad = (value: number) => String(value).padStart(2, '0');

function keyOf(year: number, month: number, day: number): string {
  return `${year}-${pad(month)}-${pad(day)}`;
}

function parseKey(key: string): [number, number, number] {
  const [year = 0, month = 1, day = 1] = key.split('-').map(Number);
  return [year, month, day];
}

const DATE_KEY = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

/** True for a well-formed `YYYY-MM-DD` that names a real calendar day. */
export function isDateKey(value: string): boolean {
  if (!DATE_KEY.test(value)) return false;
  const [year, month, day] = parseKey(value);
  return new Date(Date.UTC(year, month - 1, day)).getUTCDate() === day;
}

/** The practice's calendar day of an instant. */
export function dateKey(date: Date): string {
  const { year, month, day } = zonedParts(date);
  return keyOf(year, month, day);
}

/** Hour (0-23) of an instant in the practice time zone. */
export function practiceHour(date: Date): number {
  return zonedParts(date).hour;
}

/** Calendar arithmetic on date keys; independent of time zones and DST. */
export function addDays(key: string, days: number): string {
  const [year, month, day] = parseKey(key);
  const date = new Date(Date.UTC(year, month - 1, day + days));
  return keyOf(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate());
}

/** Monday of the week that contains `key` (ISO weeks start on Monday). */
export function mondayOf(key: string): string {
  const [year, month, day] = parseKey(key);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return addDays(key, -((weekday + 6) % 7));
}

/** Days between two date keys (`to - from`). */
export function daysBetween(from: string, to: string): number {
  const [y1, m1, d1] = parseKey(from);
  const [y2, m2, d2] = parseKey(to);
  return Math.round((Date.UTC(y2, m2 - 1, d2) - Date.UTC(y1, m1 - 1, d1)) / DAY_MS);
}

/** Offset of the practice time zone from UTC at `date`, in milliseconds. */
function offsetAt(date: Date): number {
  const p = zonedParts(date);
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  return asUtc - Math.floor(date.getTime() / 1000) * 1000;
}

/**
 * The instant the practice's day `key` starts. Converted per date, so a week that contains a DST
 * change still starts and ends at local midnight. Midnight always exists in Europe/Berlin (the
 * clocks change at 02:00/03:00), so two passes settle the offset.
 */
export function startOfDay(key: string): Date {
  const [year, month, day] = parseKey(key);
  const guess = Date.UTC(year, month - 1, day);
  const first = guess - offsetAt(new Date(guess));
  return new Date(guess - offsetAt(new Date(first)));
}

// A date key formatted on its own (no time) is pinned to noon UTC, which is the same calendar day
// in every time zone, and formatted in UTC.
const keyDate = (key: string) => {
  const [year, month, day] = parseKey(key);
  return new Date(Date.UTC(year, month - 1, day, 12));
};

const dayFormat = (options: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat(LOCALE, { timeZone: 'UTC', ...options });

const longDay = dayFormat({ weekday: 'long', day: 'numeric', month: 'long' });
const longDayWithYear = dayFormat({
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});
const shortWeekday = dayFormat({ weekday: 'short' });
const dayOfMonth = dayFormat({ day: 'numeric' });
const shortMonth = dayFormat({ month: 'short' });
const rangeFormat = dayFormat({ day: 'numeric', month: 'long', year: 'numeric' });
const timeFormat = new Intl.DateTimeFormat(LOCALE, {
  timeZone: PRACTICE_TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

/** „Montag, 16. November“ (with the year if it is not the current one). */
export function formatDay(key: string, today: string = dateKey(new Date())): string {
  return (key.slice(0, 4) === today.slice(0, 4) ? longDay : longDayWithYear).format(keyDate(key));
}

/** „Mo“ */
export function formatWeekdayShort(key: string): string {
  return shortWeekday.format(keyDate(key)).replace('.', '');
}

/** „16.“ → „16“ */
export function formatDayOfMonth(key: string): string {
  return dayOfMonth.format(keyDate(key)).replace('.', '');
}

/** „Nov.“ */
export function formatMonthShort(key: string): string {
  return shortMonth.format(keyDate(key));
}

/** „16.–22. November 2026“, „30. November – 6. Dezember 2026“ */
export function formatWeekRange(monday: string): string {
  // ICU puts thin spaces around the dash; plain spaces match every other text.
  return rangeFormat
    .formatRange(keyDate(monday), keyDate(addDays(monday, 6)))
    .replace(/[\u2009\u202f]/g, ' ');
}

/** „08:00“ in the practice time zone. */
export function formatTime(iso: string): string {
  return timeFormat.format(new Date(iso));
}

/** „Montag, 16. November, 08:00 Uhr“ */
export function formatDateTime(iso: string, today?: string): string {
  return `${formatDay(dateKey(new Date(iso)), today)}, ${formatTime(iso)} Uhr`;
}

/** „08:00 – 08:15 Uhr“ */
export function formatTimeRange(startsAt: string, endsAt: string): string {
  return `${formatTime(startsAt)} – ${formatTime(endsAt)} Uhr`;
}

export type DayPart = 'morning' | 'afternoon' | 'evening';

export const DAY_PART_LABELS: Record<DayPart, string> = {
  morning: 'Vormittag',
  afternoon: 'Nachmittag',
  evening: 'Abend',
};

export function dayPart(iso: string): DayPart {
  const hour = practiceHour(new Date(iso));
  if (hour < 12) return 'morning';
  return hour < 17 ? 'afternoon' : 'evening';
}

/** Last moment a patient may still cancel or reschedule online (BR-11, BR-22). */
export function changeDeadline(startsAt: string, deadlineHours: number): Date {
  return new Date(new Date(startsAt).getTime() - deadlineHours * 60 * 60 * 1000);
}
