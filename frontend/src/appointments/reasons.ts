import type { components } from '../api/schema';

export type AppointmentReason = components['schemas']['AppointmentReason'];

/** Reason categories (BR-10) in the order the booking dialog offers them. No free text exists. */
export const REASONS: readonly { value: AppointmentReason; label: string }[] = [
  { value: 'CHECKUP', label: 'Vorsorgeuntersuchung' },
  { value: 'FOLLOW_UP', label: 'Kontrolltermin' },
  { value: 'CONSULTATION', label: 'Beratungsgespräch' },
  { value: 'VACCINATION', label: 'Impfung' },
  { value: 'PRESCRIPTION', label: 'Rezept' },
  { value: 'BLOOD_TEST', label: 'Blutabnahme' },
  { value: 'BLOOD_TEST_FASTING', label: 'Blutabnahme (nüchtern)' },
  { value: 'OTHER', label: 'Sonstiges' },
];

const LABELS = Object.fromEntries(REASONS.map(({ value, label }) => [value, label])) as Record<
  AppointmentReason,
  string
>;

export function reasonLabel(reason: AppointmentReason): string {
  return LABELS[reason];
}

export function isReason(value: unknown): value is AppointmentReason {
  return typeof value === 'string' && value in LABELS;
}

/** BR-10: the UI reminds the patient to come fasting. */
export const needsFasting = (reason: AppointmentReason | undefined) =>
  reason === 'BLOOD_TEST_FASTING';
