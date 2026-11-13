import { describe, expect, it } from 'vitest';
import {
  addDays,
  changeDeadline,
  dateKey,
  dayPart,
  daysBetween,
  formatDateTime,
  formatDay,
  formatTime,
  formatWeekRange,
  formatWeekdayShort,
  isDateKey,
  mondayOf,
  startOfDay,
} from './time';

describe('practice time', () => {
  it('starts a day at local midnight in winter and summer time', () => {
    expect(startOfDay('2026-01-15').toISOString()).toBe('2026-01-14T23:00:00.000Z');
    expect(startOfDay('2026-07-15').toISOString()).toBe('2026-07-14T22:00:00.000Z');
  });

  it('handles the days the clocks change', () => {
    // 29 March 2026: 02:00 CET becomes 03:00 CEST; 25 October 2026: back again.
    expect(startOfDay('2026-03-29').toISOString()).toBe('2026-03-28T23:00:00.000Z');
    expect(startOfDay('2026-03-30').toISOString()).toBe('2026-03-29T22:00:00.000Z');
    expect(startOfDay('2026-10-25').toISOString()).toBe('2026-10-24T22:00:00.000Z');
    expect(startOfDay('2026-10-26').toISOString()).toBe('2026-10-25T23:00:00.000Z');
  });

  it('names the practice day of an instant, not the UTC day', () => {
    expect(dateKey(new Date('2026-11-15T23:30:00Z'))).toBe('2026-11-16');
    expect(dateKey(new Date('2026-07-15T21:59:00Z'))).toBe('2026-07-15');
  });

  it('does calendar arithmetic across months, years and DST', () => {
    expect(addDays('2026-12-30', 3)).toBe('2027-01-02');
    expect(addDays('2026-03-28', 2)).toBe('2026-03-30');
    expect(mondayOf('2026-11-15')).toBe('2026-11-09');
    expect(mondayOf('2026-11-16')).toBe('2026-11-16');
    expect(daysBetween('2026-11-16', '2027-11-16')).toBe(365);
  });

  it('accepts only real dates as keys', () => {
    expect(isDateKey('2026-11-16')).toBe(true);
    expect(isDateKey('2026-02-30')).toBe(false);
    expect(isDateKey('16.11.2026')).toBe(false);
  });

  it('formats in German in the practice time zone', () => {
    expect(formatTime('2026-11-16T07:00:00Z')).toBe('08:00');
    expect(formatTime('2026-07-16T07:00:00Z')).toBe('09:00');
    expect(formatDay('2026-11-16', '2026-11-13')).toBe('Montag, 16. November');
    expect(formatDay('2027-01-04', '2026-11-13')).toBe('Montag, 4. Januar 2027');
    expect(formatWeekdayShort('2026-11-16')).toBe('Mo');
    expect(formatDateTime('2026-11-16T07:00:00Z', '2026-11-13')).toBe(
      'Montag, 16. November, 08:00 Uhr',
    );
    expect(formatWeekRange('2026-11-16')).toBe('16.–22. November 2026');
    expect(formatWeekRange('2026-11-30')).toBe('30. November – 6. Dezember 2026');
  });

  it('sorts times into parts of the day', () => {
    expect(dayPart('2026-11-16T10:45:00Z')).toBe('morning');
    expect(dayPart('2026-11-16T11:00:00Z')).toBe('afternoon');
    expect(dayPart('2026-11-16T16:00:00Z')).toBe('evening');
  });

  it('computes the online change deadline', () => {
    expect(changeDeadline('2026-11-16T07:00:00Z', 24).toISOString()).toBe(
      '2026-11-15T07:00:00.000Z',
    );
  });
});
