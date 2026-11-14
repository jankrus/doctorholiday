import { AlertDialog, Button, Card, Flex, Heading, Link, Text } from '@radix-ui/themes';
import type { ReactNode } from 'react';
import { useEffect, useRef } from 'react';
import {
  Link as RouterLink,
  useFetcher,
  useLoaderData,
  type ActionFunctionArgs,
  useRouteLoaderData,
  type LoaderFunctionArgs,
} from 'react-router';
import { api, type SessionInfo } from '../../api/client';
import { errorMessage } from '../../api/errors';
import {
  fetchMyAppointments,
  fetchRecentAppointments,
  findNextAvailable,
  type Appointment,
  type AvailableTime,
} from '../../appointments/api';
import { reasonLabel } from '../../appointments/reasons';
import {
  changeDeadline,
  dateKey,
  daysBetween,
  formatDateTime,
  formatDay,
  formatTime,
  formatTimeRange,
  greeting,
  mondayOf,
  relativeDay,
} from '../../appointments/time';
import { requireRole } from '../../auth/guards';
import { AppointmentCard } from '../../components/appointments/AppointmentCard';
import { AppointmentHistory } from '../../components/appointments/AppointmentHistory';
import {
  ArrowRightIcon,
  CalendarEmptyIcon,
  CalendarIcon,
  CancelIcon,
  ClockIcon,
  HistoryIcon,
  InfoIcon,
  PhoneIcon,
  PlusIcon,
  RescheduleIcon,
  ShieldIcon,
} from '../../components/icons';
import { Notice } from '../../components/Notice';
import { usePracticeSettings } from '../AppLayout';
import { OPEN_APPOINTMENT_LIMIT } from './BookPage';
import './AppointmentsPage.css';

type AppointmentsData = {
  today: string;
  upcoming: Appointment[];
  /** Past appointments and cancelled future ones, newest first. */
  history: Appointment[];
  /** First free time from now on; `null` if none within a year, `undefined` if unknown. */
  nextFree?: AvailableTime | null;
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
    const [upcoming, cancelledAhead, past, nextFree] = await Promise.all([
      fetchMyAppointments({ status: 'BOOKED', from: now }),
      fetchMyAppointments({ status: 'CANCELLED', from: now }),
      fetchRecentAppointments(now),
      // Only a shortcut on the overview; the page works without it.
      findNextAvailable(now).catch(() => undefined),
    ]);
    const history = [...cancelledAhead, ...past].sort((a, b) =>
      b.startsAt.localeCompare(a.startsAt),
    );
    return { today, upcoming, history, nextFree };
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
  const { today, upcoming, history, nextFree, error } = useLoaderData<AppointmentsData>();
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
      <Welcome today={today} next={error ? undefined : (upcoming[0] ?? null)} />

      {error && <Notice tone="error">{error}</Notice>}
      {cancelled && (
        <div ref={noticeRef} tabIndex={-1} className="appointments__notice">
          <Notice tone="success">
            Ihr Termin am {formatDateTime(cancelled.startsAt, today)} wurde abgesagt.
          </Notice>
        </div>
      )}

      {!error && (
        <Overview today={today} upcoming={upcoming} history={history} nextFree={nextFree} />
      )}

      <div className="dashboard__columns">
        <section aria-labelledby="upcoming-heading" className="dashboard__main">
          <Heading as="h2" size="5" mb="3" id="upcoming-heading">
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
                      featured={index === 0}
                    />
                  </li>
                ))}
              </ul>
            </Flex>
          )}
        </section>

        <div className="dashboard__side">
          <Card size="3" asChild>
            <section aria-labelledby="history-heading">
              <SideHeading id="history-heading" icon={<HistoryIcon />}>
                Verlauf
              </SideHeading>
              {history.length > 0 ? (
                <AppointmentHistory appointments={history} today={today} />
              ) : (
                <Text as="p" size="2" color="gray">
                  Vergangene und abgesagte Termine erscheinen hier.
                </Text>
              )}
            </section>
          </Card>
          <Card size="3" asChild>
            <section aria-labelledby="hints-heading">
              <SideHeading id="hints-heading" icon={<InfoIcon />}>
                Gut zu wissen
              </SideHeading>
              <Hints deadlineHours={deadlineHours} />
            </section>
          </Card>
        </div>
      </div>
    </Flex>
  );
}

/** „Guten Morgen, Erika Mustermann“, today's date and one sentence about the next appointment. */
function Welcome({ today, next }: { today: string; next: Appointment | null | undefined }) {
  const session = useRouteLoaderData<SessionInfo | null>('root');
  const name = session?.user?.displayName;

  let summary = 'Hier sehen Sie Ihre Termine auf einen Blick.';
  if (next === null) summary = 'Sie haben derzeit keine anstehenden Termine.';
  if (next) {
    const day = dateKey(new Date(next.startsAt));
    const when =
      daysBetween(today, day) <= 2 ? relativeDay(day, today) : `am ${formatDay(day, today)}`;
    summary = `Ihr nächster Termin ist ${when} um ${formatTime(next.startsAt)} Uhr bei ${next.doctor.displayName}.`;
  }

  return (
    <div className="welcome">
      <Flex
        direction={{ initial: 'column', md: 'row' }}
        justify="between"
        align={{ initial: 'start', md: 'end' }}
        gap="5"
        className="welcome__content"
      >
        <Flex direction="column" gap="2">
          <Text size="2" weight="medium" className="welcome__date">
            {formatDay(today, today)}
          </Text>
          <Heading as="h1" size={{ initial: '7', sm: '8' }} className="welcome__title">
            {greeting()}
            {name && `, ${name}`}
          </Heading>
          <Text as="p" size="3" className="welcome__summary">
            {summary}
          </Text>
        </Flex>
        <Button asChild size="3">
          <RouterLink to="/appointments/book">
            <PlusIcon />
            Termin buchen
          </RouterLink>
        </Button>
      </Flex>
    </div>
  );
}

type OverviewProps = Pick<AppointmentsData, 'today' | 'upcoming' | 'history' | 'nextFree'>;

/** Three tiles: open appointments against the limit, the next free time, the last visit. */
function Overview({ today, upcoming, history, nextFree }: OverviewProps) {
  // Booked appointments in the history all lie in the past.
  const lastVisit = history.find((appointment) => appointment.status === 'BOOKED');
  const open = Math.min(upcoming.length, OPEN_APPOINTMENT_LIMIT);

  return (
    <ul className="overview" aria-label="Übersicht">
      <OverviewTile icon={<CalendarIcon />} label="Offene Termine">
        <Text as="p" size="6" weight="bold" className="overview__value">
          {upcoming.length}{' '}
          <Text size="3" weight="regular" color="gray">
            von {OPEN_APPOINTMENT_LIMIT}
          </Text>
        </Text>
        <div className="overview__meter" aria-hidden="true">
          {Array.from({ length: OPEN_APPOINTMENT_LIMIT }, (_, index) => (
            <span key={index} className={index < open ? 'overview__segment--filled' : undefined} />
          ))}
        </div>
        <Text as="p" size="2" color="gray">
          {upcoming.length >= OPEN_APPOINTMENT_LIMIT
            ? 'Mehr gleichzeitig gebuchte Termine sind nicht möglich.'
            : `Sie können noch ${OPEN_APPOINTMENT_LIMIT - upcoming.length} weitere buchen.`}
        </Text>
      </OverviewTile>

      {nextFree !== undefined && (
        <OverviewTile icon={<ClockIcon />} label="Nächster freier Termin">
          {nextFree ? (
            <>
              <Text as="p" size="5" weight="bold" className="overview__value">
                {formatDay(dateKey(new Date(nextFree.startsAt)), today)}
              </Text>
              <Text as="p" size="2" color="gray">
                {formatTime(nextFree.startsAt)} Uhr · {nextFree.doctor.displayName}
              </Text>
              <Link asChild size="2" weight="medium" className="overview__link">
                <RouterLink
                  to={`/appointments/book?week=${mondayOf(dateKey(new Date(nextFree.startsAt)))}`}
                >
                  Freie Termine ansehen
                  <ArrowRightIcon />
                </RouterLink>
              </Link>
            </>
          ) : (
            <>
              <Text as="p" size="5" weight="bold" className="overview__value">
                Derzeit keiner
              </Text>
              <Text as="p" size="2" color="gray">
                In den nächsten 12 Monaten ist online nichts frei. Bitte wenden Sie sich an die
                Praxis.
              </Text>
            </>
          )}
        </OverviewTile>
      )}

      <OverviewTile icon={<HistoryIcon />} label="Letzter Besuch">
        {lastVisit ? (
          <>
            <Text as="p" size="5" weight="bold" className="overview__value">
              {formatDay(dateKey(new Date(lastVisit.startsAt)), today)}
            </Text>
            <Text as="p" size="2" color="gray">
              {reasonLabel(lastVisit.reason)} · {lastVisit.doctor.displayName}
            </Text>
            <Text as="p" size="2" color="gray">
              {capitalize(relativeDay(dateKey(new Date(lastVisit.startsAt)), today))},{' '}
              {formatTimeRange(lastVisit.startsAt, lastVisit.endsAt)}
            </Text>
          </>
        ) : (
          <>
            <Text as="p" size="5" weight="bold" className="overview__value">
              Noch keiner
            </Text>
            <Text as="p" size="2" color="gray">
              Nach Ihrem ersten Termin sehen Sie ihn hier.
            </Text>
          </>
        )}
      </OverviewTile>
    </ul>
  );
}

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

function OverviewTile({
  icon,
  label,
  children,
}: {
  icon: ReactNode;
  label: string;
  children: ReactNode;
}) {
  return (
    <li>
      <Card size={{ initial: '2', sm: '3' }} className="overview__tile">
        <Flex direction="column" gap="2">
          <Flex align="center" gap="2" mb="1">
            <span className="overview__icon">{icon}</span>
            <Text size="2" weight="medium" color="gray">
              {label}
            </Text>
          </Flex>
          {children}
        </Flex>
      </Card>
    </li>
  );
}

function SideHeading({ id, icon, children }: { id: string; icon: ReactNode; children: string }) {
  return (
    <Flex align="center" gap="2" mb="4">
      <span className="dashboard__side-icon">{icon}</span>
      <Heading as="h2" size="4" id={id}>
        {children}
      </Heading>
    </Flex>
  );
}

/** Practice rules the patient should know, and where to go in an emergency. */
function Hints({ deadlineHours }: { deadlineHours: number | null }) {
  return (
    <ul className="hints">
      {deadlineHours !== null && (
        <Hint icon={<RescheduleIcon />}>
          {deadlineHours > 0
            ? `Verschieben oder absagen können Sie online bis ${deadlineHours} Stunden vor Beginn.`
            : 'Verschieben oder absagen können Sie online bis zum Beginn.'}{' '}
          Danach hilft Ihnen die Praxis weiter.
        </Hint>
      )}
      <Hint icon={<CalendarIcon />}>
        Sie können bis zu {OPEN_APPOINTMENT_LIMIT} Termine gleichzeitig gebucht haben.
      </Hint>
      <Hint icon={<ShieldIcon />}>
        Den Grund wählen Sie aus festen Kategorien. Beschwerden besprechen Sie persönlich in der
        Praxis.
      </Hint>
      <Hint icon={<PhoneIcon />} tone="urgent">
        Im Notfall: <Link href="tel:112">112</Link>. Ärztlicher Bereitschaftsdienst:{' '}
        <Link href="tel:116117">116 117</Link>.
      </Hint>
    </ul>
  );
}

function Hint({ icon, tone, children }: { icon: ReactNode; tone?: 'urgent'; children: ReactNode }) {
  return (
    <li className="hints__item">
      <span className={tone === 'urgent' ? 'hints__icon hints__icon--urgent' : 'hints__icon'}>
        {icon}
      </span>
      <Text as="p" size="2">
        {children}
      </Text>
    </li>
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
  featured?: boolean;
};

function UpcomingAppointment({ appointment, today, deadlineHours, featured }: UpcomingProps) {
  // Without settings the server still decides; the buttons stay and report a passed deadline.
  const deadline =
    deadlineHours === null ? null : changeDeadline(appointment.startsAt, deadlineHours);
  const changeable = deadline === null || Date.now() <= deadline.getTime();

  return (
    <AppointmentCard
      appointment={appointment}
      today={today}
      highlight={featured ? 'Nächster Termin' : undefined}
      when={relativeDay(dateKey(new Date(appointment.startsAt)), today)}
      featured={featured}
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
