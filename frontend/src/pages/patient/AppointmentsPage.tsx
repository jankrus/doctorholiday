import { AlertDialog, Button, Card, Flex, Heading, Link, Text } from '@radix-ui/themes';
import { useEffect, useRef } from 'react';
import {
  Link as RouterLink,
  useFetcher,
  useLoaderData,
  type ActionFunctionArgs,
  type LoaderFunctionArgs,
} from 'react-router';
import { api } from '../../api/client';
import { errorMessage } from '../../api/errors';
import {
  fetchMyAppointments,
  fetchRecentAppointments,
  type Appointment,
} from '../../appointments/api';
import { changeDeadline, dateKey, formatDateTime } from '../../appointments/time';
import { requireRole } from '../../auth/guards';
import { AppointmentCard } from '../../components/appointments/AppointmentCard';
import {
  CalendarEmptyIcon,
  CancelIcon,
  InfoIcon,
  PlusIcon,
  RescheduleIcon,
} from '../../components/icons';
import { Notice } from '../../components/Notice';
import { usePracticeSettings } from '../AppLayout';
import { PatientPageHeader } from './PatientPageHeader';
import './AppointmentsPage.css';

type AppointmentsData = {
  today: string;
  upcoming: Appointment[];
  /** Past appointments and cancelled future ones, newest first. */
  history: Appointment[];
  error?: string;
};

type CancelResult = { cancelled: Appointment } | { error: string; id: string };

const CANCEL_FETCHER = 'cancel-appointment';
const guard = requireRole(['PATIENT']);

export async function appointmentsLoader(
  args: LoaderFunctionArgs,
): Promise<AppointmentsData | Response> {
  const redirect = await guard(args);
  if (redirect instanceof Response) return redirect;
  const now = new Date();
  const today = dateKey(now);
  try {
    const [upcoming, cancelledAhead, past] = await Promise.all([
      fetchMyAppointments({ status: 'BOOKED', from: now }),
      fetchMyAppointments({ status: 'CANCELLED', from: now }),
      fetchRecentAppointments(now),
    ]);
    const history = [...cancelledAhead, ...past].sort((a, b) =>
      b.startsAt.localeCompare(a.startsAt),
    );
    return { today, upcoming, history };
  } catch (error) {
    return { today, upcoming: [], history: [], error: errorMessage(error) };
  }
}

/** Cancels one of the patient's appointments (A09); the time becomes available again. */
export async function appointmentsAction({ request }: ActionFunctionArgs): Promise<CancelResult> {
  const form = await request.formData();
  const id = String(form.get('id') ?? '');
  try {
    const { data, error } = await api.POST('/api/v1/appointments/{id}/cancel', {
      params: { path: { id } },
    });
    if (data) return { cancelled: data };
    return { error: errorMessage(error), id };
  } catch {
    return { error: errorMessage(null), id };
  }
}

export function AppointmentsPage() {
  const { today, upcoming, history, error } = useLoaderData<AppointmentsData>();
  const settings = usePracticeSettings();
  const deadlineHours = settings?.cancellationDeadlineHours ?? null;
  const cancel = useFetcher<CancelResult>({ key: CANCEL_FETCHER });
  const cancelled = cancel.data && 'cancelled' in cancel.data ? cancel.data.cancelled : undefined;
  const noticeRef = useRef<HTMLDivElement>(null);

  // The dialog closes with its card; focus moves to the confirmation instead of the page start.
  useEffect(() => {
    if (cancelled) noticeRef.current?.focus();
  }, [cancelled]);

  return (
    <Flex direction="column" gap="6">
      <PatientPageHeader
        title="Meine Termine"
        action={
          <Button asChild size="3">
            <RouterLink to="/appointments/book">
              <PlusIcon />
              Termin buchen
            </RouterLink>
          </Button>
        }
      >
        {deadlineHours === null
          ? 'Ihre gebuchten Termine auf einen Blick.'
          : deadlineHours > 0
            ? `Ihre gebuchten Termine auf einen Blick. Bis ${deadlineHours} Stunden vor Beginn können Sie einen Termin hier verschieben oder absagen.`
            : 'Ihre gebuchten Termine auf einen Blick. Bis zum Beginn können Sie einen Termin hier verschieben oder absagen.'}
      </PatientPageHeader>

      {error && <Notice tone="error">{error}</Notice>}
      {cancelled && (
        <div ref={noticeRef} tabIndex={-1} className="appointments__notice">
          <Notice tone="success">
            Ihr Termin am {formatDateTime(cancelled.startsAt, today)} wurde abgesagt.
          </Notice>
        </div>
      )}

      <section aria-labelledby="upcoming-heading">
        <Heading as="h2" size="4" mb="3" id="upcoming-heading">
          Anstehende Termine
        </Heading>
        {upcoming.length === 0 && !error ? (
          <EmptyState />
        ) : (
          <Flex direction="column" gap="3" asChild>
            <ul className="appointments__list">
              {upcoming.map((appointment, index) => (
                <li key={appointment.id}>
                  <UpcomingAppointment
                    appointment={appointment}
                    today={today}
                    deadlineHours={deadlineHours}
                    highlight={index === 0 ? 'Nächster Termin' : undefined}
                  />
                </li>
              ))}
            </ul>
          </Flex>
        )}
      </section>

      {history.length > 0 && (
        <details className="appointments__history">
          <summary>
            <Text size="3" weight="medium">
              Vergangene und abgesagte Termine ({history.length})
            </Text>
          </summary>
          <Flex direction="column" gap="3" mt="3" asChild>
            <ul className="appointments__list">
              {history.map((appointment) => (
                <li key={appointment.id}>
                  <AppointmentCard appointment={appointment} today={today} muted />
                </li>
              ))}
            </ul>
          </Flex>
        </details>
      )}
    </Flex>
  );
}

function EmptyState() {
  return (
    <Card size="4">
      <Flex direction="column" align="center" gap="3" py="4" className="appointments__empty">
        <span className="appointments__empty-icon">
          <CalendarEmptyIcon size={28} />
        </span>
        <Text as="p" size="4" weight="bold" align="center">
          Sie haben keine anstehenden Termine.
        </Text>
        <Text as="p" size="2" color="gray" align="center">
          Freie Termine finden und buchen Sie in wenigen Schritten.
        </Text>
        <Button asChild size="3" mt="2">
          <RouterLink to="/appointments/book">
            <PlusIcon />
            Termin buchen
          </RouterLink>
        </Button>
      </Flex>
    </Card>
  );
}

type UpcomingProps = {
  appointment: Appointment;
  today: string;
  deadlineHours: number | null;
  highlight?: string;
};

function UpcomingAppointment({ appointment, today, deadlineHours, highlight }: UpcomingProps) {
  // Without settings the server still decides; the buttons stay and report a passed deadline.
  const deadline =
    deadlineHours === null ? null : changeDeadline(appointment.startsAt, deadlineHours);
  const changeable = deadline === null || Date.now() <= deadline.getTime();

  return (
    <AppointmentCard
      appointment={appointment}
      today={today}
      highlight={highlight}
      footer={
        deadline &&
        (changeable ? (
          <Text as="p" size="2" color="gray">
            Änderbar bis {formatDateTime(deadline.toISOString(), today)}
          </Text>
        ) : (
          <Text as="p" size="2" className="appointments__locked">
            <InfoIcon />
            Online nicht mehr änderbar. Bitte wenden Sie sich an die Praxis.
          </Text>
        ))
      }
      actions={
        changeable && (
          <>
            <Button asChild variant="soft" size="2">
              <RouterLink to={`/appointments/${appointment.id}/reschedule`}>
                <RescheduleIcon />
                Verschieben
              </RouterLink>
            </Button>
            <CancelDialog appointment={appointment} today={today} />
          </>
        )
      }
    />
  );
}

function CancelDialog({ appointment, today }: { appointment: Appointment; today: string }) {
  const fetcher = useFetcher<CancelResult>({ key: CANCEL_FETCHER });
  const submitting = fetcher.state !== 'idle' && fetcher.formData?.get('id') === appointment.id;
  const failure =
    fetcher.data && 'error' in fetcher.data && fetcher.data.id === appointment.id
      ? fetcher.data.error
      : undefined;

  return (
    <AlertDialog.Root>
      <AlertDialog.Trigger>
        <Button variant="soft" color="gray" size="2">
          <CancelIcon />
          Absagen
        </Button>
      </AlertDialog.Trigger>
      <AlertDialog.Content maxWidth="480px">
        <fetcher.Form method="post" action="/appointments">
          <input type="hidden" name="id" value={appointment.id} />
          <Flex direction="column" gap="4">
            <AlertDialog.Title size="5" mb="0">
              Termin absagen?
            </AlertDialog.Title>
            <AlertDialog.Description size="3">
              {formatDateTime(appointment.startsAt, today)} bei {appointment.doctor.displayName}.
              Die Uhrzeit wird danach für andere Patientinnen und Patienten freigegeben.
            </AlertDialog.Description>
            {failure && <Notice tone="error">{failure}</Notice>}
            <Text as="p" size="2" color="gray">
              Sie möchten nur eine andere Uhrzeit?{' '}
              <Link asChild weight="medium">
                <RouterLink to={`/appointments/${appointment.id}/reschedule`}>
                  Verschieben Sie den Termin
                </RouterLink>
              </Link>
              , dann bleibt er bestehen, bis der neue feststeht.
            </Text>
            <Flex direction={{ initial: 'column-reverse', xs: 'row' }} gap="3" justify="end">
              <AlertDialog.Cancel>
                <Button type="button" variant="soft" color="gray" size="3">
                  Termin behalten
                </Button>
              </AlertDialog.Cancel>
              <Button type="submit" color="red" size="3" loading={submitting}>
                Termin absagen
              </Button>
            </Flex>
          </Flex>
        </fetcher.Form>
      </AlertDialog.Content>
    </AlertDialog.Root>
  );
}
