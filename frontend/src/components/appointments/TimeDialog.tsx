import { Button, Callout, DataList, Dialog, Flex, RadioCards, Text } from '@radix-ui/themes';
import { useEffect, useId, useRef, useState } from 'react';
import { Link as RouterLink, useFetcher } from 'react-router';
import type { Appointment } from '../../appointments/api';
import {
  needsFasting,
  reasonLabel,
  REASONS,
  type AppointmentReason,
} from '../../appointments/reasons';
import {
  changeDeadline,
  dateKey,
  formatDateTime,
  formatDay,
  formatTimeRange,
} from '../../appointments/time';
import { AlertIcon, InfoIcon, SuccessIcon } from '../icons';
import '../FormField.css';
import { Notice } from '../Notice';
import type { TimeOption } from './AvailabilityBrowser';
import './TimeDialog.css';

/** What the book and reschedule actions return to the dialog. */
export type TimeActionResult =
  { appointment: Appointment } | { error: string; conflict?: boolean; fieldError?: string };

type Props = {
  mode: 'book' | 'reschedule';
  option: TimeOption;
  /** The appointment being moved (reschedule only). */
  current?: Appointment;
  /** `cancellationDeadlineHours`, or `null` if the settings could not be loaded. */
  deadlineHours: number | null;
  today: string;
  /** `done` is true once the appointment was booked or moved. */
  onClose: (done: boolean) => void;
};

const TEXT = {
  book: {
    title: 'Termin buchen',
    submit: 'Termin verbindlich buchen',
    done: 'Ihr Termin ist gebucht',
  },
  reschedule: {
    title: 'Termin verschieben',
    submit: 'Termin verschieben',
    done: 'Ihr Termin wurde verschoben',
  },
};

/**
 * Confirms a chosen time: doctor (if several are free), reason category (booking only, BR-10),
 * the fasting hint and the online change deadline, then sends it to the route's action. A time
 * that was taken meanwhile (409) is reported here, and the route reloads the free times.
 */
export function TimeDialog({ mode, option, current, deadlineHours, today, onClose }: Props) {
  const fetcher = useFetcher<TimeActionResult>();
  const result = fetcher.data;
  const done = result && 'appointment' in result ? result.appointment : undefined;
  const failure = result && 'error' in result ? result : undefined;
  const submitting = fetcher.state !== 'idle';
  const [doctorId, setDoctorId] = useState(option.doctors[0]?.id ?? '');
  const [reason, setReason] = useState<AppointmentReason | ''>('');
  const reasonLabelId = useId();
  const doctorLabelId = useId();
  const reasonError = failure?.fieldError;
  const reasonRef = useRef<HTMLDivElement>(null);
  const text = TEXT[mode];

  useEffect(() => {
    // Validate on submit: after a missing reason, focus moves to the group (form behaviour 2).
    if (reasonError) reasonRef.current?.querySelector<HTMLElement>('button')?.focus();
  }, [reasonError, result]);

  const deadline = deadlineHours === null ? null : changeDeadline(option.startsAt, deadlineHours);
  const deadlinePassed = deadline !== null && deadline.getTime() < Date.now();
  const day = formatDay(dateKey(new Date(option.startsAt)), today);
  const doctor = option.doctors.find(({ id }) => id === doctorId);
  const fasting = needsFasting(mode === 'book' ? reason || undefined : current?.reason);

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose(Boolean(done))}>
      <Dialog.Content maxWidth="520px" aria-describedby={undefined}>
        {done ? (
          <Flex direction="column" gap="5">
            <Flex direction="column" align="center" gap="3" pt="2">
              <span className="time-dialog__done-icon">
                <SuccessIcon size={32} />
              </span>
              <Dialog.Title size="6" align="center" mb="0">
                {text.done}
              </Dialog.Title>
              <Text as="p" size="3" color="gray" align="center" role="status">
                {formatDateTime(done.startsAt, today)} bei {done.doctor.displayName}
              </Text>
            </Flex>
            {needsFasting(done.reason) && <FastingHint />}
            {deadline && !deadlinePassed && (
              <Text as="p" size="2" color="gray" align="center">
                Online absagen oder verschieben können Sie bis{' '}
                {formatDateTime(deadline.toISOString(), today)}.
              </Text>
            )}
            <Flex direction={{ initial: 'column-reverse', xs: 'row' }} gap="3" justify="end">
              {mode === 'book' && (
                <Button variant="soft" color="gray" size="3" onClick={() => onClose(true)}>
                  Weiteren Termin buchen
                </Button>
              )}
              <Button asChild size="3">
                <RouterLink to="/appointments">Zu meinen Terminen</RouterLink>
              </Button>
            </Flex>
          </Flex>
        ) : failure?.conflict ? (
          // Taken meanwhile (409): retrying cannot work, so the only way on is another time. The
          // route has already reloaded the free times behind the dialog.
          <Flex direction="column" gap="5">
            <Dialog.Title size="6" mb="0">
              {text.title}
            </Dialog.Title>
            <Notice tone="error">{failure.error}</Notice>
            <Text as="p" size="3" color="gray">
              {day}, {formatTimeRange(option.startsAt, option.endsAt)}
            </Text>
            <Flex justify="end">
              <Button size="3" onClick={() => onClose(false)} autoFocus>
                Andere Uhrzeit wählen
              </Button>
            </Flex>
          </Flex>
        ) : (
          <fetcher.Form method="post" noValidate>
            <input type="hidden" name="startsAt" value={option.startsAt} />
            <input type="hidden" name="doctorId" value={doctorId} />
            <Flex direction="column" gap="5">
              <Dialog.Title size="6" mb="0">
                {text.title}
              </Dialog.Title>

              {failure && !failure.fieldError && <Notice tone="error">{failure.error}</Notice>}

              <DataList.Root orientation={{ initial: 'vertical', xs: 'horizontal' }} size="2">
                {current && (
                  <DataList.Item>
                    <DataList.Label minWidth="120px">Bisher</DataList.Label>
                    <DataList.Value>
                      <Text color="gray" className="time-dialog__old">
                        {formatDateTime(current.startsAt, today)}, {current.doctor.displayName}
                      </Text>
                    </DataList.Value>
                  </DataList.Item>
                )}
                <DataList.Item>
                  <DataList.Label minWidth="120px">{current ? 'Neuer Tag' : 'Tag'}</DataList.Label>
                  <DataList.Value>
                    <Text weight="medium">{day}</Text>
                  </DataList.Value>
                </DataList.Item>
                <DataList.Item>
                  <DataList.Label minWidth="120px">Uhrzeit</DataList.Label>
                  <DataList.Value>
                    <Text weight="medium">{formatTimeRange(option.startsAt, option.endsAt)}</Text>
                  </DataList.Value>
                </DataList.Item>
                {option.doctors.length === 1 && (
                  <DataList.Item>
                    <DataList.Label minWidth="120px">Ärztin/Arzt</DataList.Label>
                    <DataList.Value>
                      <Text weight="medium">{doctor?.displayName}</Text>
                    </DataList.Value>
                  </DataList.Item>
                )}
                {current && (
                  <DataList.Item>
                    <DataList.Label minWidth="120px">Grund</DataList.Label>
                    <DataList.Value>{reasonLabel(current.reason)}</DataList.Value>
                  </DataList.Item>
                )}
              </DataList.Root>

              {option.doctors.length > 1 && (
                <Flex direction="column" gap="2">
                  <Text id={doctorLabelId} size="2" weight="medium">
                    Bei wem möchten Sie den Termin?
                  </Text>
                  <RadioCards.Root
                    value={doctorId}
                    onValueChange={setDoctorId}
                    aria-labelledby={doctorLabelId}
                    columns={{ initial: '1', xs: '2' }}
                    gap="2"
                  >
                    {option.doctors.map((d) => (
                      <RadioCards.Item key={d.id} value={d.id}>
                        {d.displayName}
                      </RadioCards.Item>
                    ))}
                  </RadioCards.Root>
                </Flex>
              )}

              {mode === 'book' && (
                <Flex direction="column" gap="2">
                  <Text id={reasonLabelId} size="2" weight="medium">
                    Grund des Termins
                  </Text>
                  <RadioCards.Root
                    ref={reasonRef}
                    name="reason"
                    value={reason}
                    onValueChange={(value) => setReason(value as AppointmentReason)}
                    aria-labelledby={reasonLabelId}
                    aria-describedby={`${reasonLabelId}-message`}
                    aria-invalid={reasonError ? true : undefined}
                    aria-required
                    columns={{ initial: '1', xs: '2' }}
                    gap="2"
                    size="1"
                  >
                    {REASONS.map(({ value, label }) => (
                      <RadioCards.Item key={value} value={value} className="time-dialog__reason">
                        {label}
                      </RadioCards.Item>
                    ))}
                  </RadioCards.Root>
                  {reasonError ? (
                    <Text
                      id={`${reasonLabelId}-message`}
                      size="2"
                      color="red"
                      className="form-field__error"
                    >
                      <AlertIcon size={16} />
                      {reasonError}
                    </Text>
                  ) : (
                    <Text id={`${reasonLabelId}-message`} size="2" color="gray">
                      Nur eine Kategorie, keine Beschwerden: Details besprechen Sie in der Praxis.
                    </Text>
                  )}
                </Flex>
              )}

              {fasting && <FastingHint />}

              {deadline &&
                (deadlinePassed ? (
                  <Callout.Root color="amber" highContrast size="1">
                    <Callout.Icon>
                      <InfoIcon />
                    </Callout.Icon>
                    <Callout.Text>
                      Dieser Termin beginnt in weniger als {deadlineHours} Stunden. Online absagen
                      oder verschieben ist danach nicht mehr möglich.
                    </Callout.Text>
                  </Callout.Root>
                ) : (
                  <Text as="p" size="2" color="gray">
                    Online absagen oder verschieben können Sie bis{' '}
                    {formatDateTime(deadline.toISOString(), today)}.
                    {current &&
                      ' Ihr bisheriger Termin bleibt bestehen, bis der neue bestätigt ist.'}
                  </Text>
                ))}

              <Flex direction={{ initial: 'column-reverse', xs: 'row' }} gap="3" justify="end">
                <Dialog.Close>
                  <Button type="button" variant="soft" color="gray" size="3">
                    Abbrechen
                  </Button>
                </Dialog.Close>
                <Button type="submit" size="3" loading={submitting}>
                  {text.submit}
                </Button>
              </Flex>
            </Flex>
          </fetcher.Form>
        )}
      </Dialog.Content>
    </Dialog.Root>
  );
}

export function FastingHint() {
  return (
    <Callout.Root color="amber" highContrast size="1">
      <Callout.Icon>
        <InfoIcon />
      </Callout.Icon>
      <Callout.Text>
        <strong>Bitte kommen Sie nüchtern.</strong> Für diese Blutabnahme sollten Sie vorher nichts
        essen. Fragen dazu beantwortet Ihnen gern die Praxis.
      </Callout.Text>
    </Callout.Root>
  );
}
