import { Button, Callout, Card, Flex, Text } from '@radix-ui/themes';
import { useState } from 'react';
import {
  Link as RouterLink,
  useLoaderData,
  useNavigate,
  type ActionFunctionArgs,
  type LoaderFunctionArgs,
} from 'react-router';
import { api } from '../../api/client';
import { errorMessage, isTimeConflict } from '../../api/errors';
import { fetchMyAppointments, type Appointment } from '../../appointments/api';
import { loadAvailability, type BrowserData } from '../../appointments/availability';
import { changeDeadline, dateKey, mondayOf } from '../../appointments/time';
import { requireRole } from '../../auth/guards';
import { AppointmentCard } from '../../components/appointments/AppointmentCard';
import {
  AvailabilityBrowser,
  type TimeOption,
} from '../../components/appointments/AvailabilityBrowser';
import { TimeDialog, type TimeActionResult } from '../../components/appointments/TimeDialog';
import { InfoIcon } from '../../components/icons';
import { Notice } from '../../components/Notice';
import { usePracticeSettings } from '../AppLayout';
import { PatientPageHeader } from './PatientPageHeader';

type RescheduleData =
  (BrowserData & { current: Appointment }) | { current: null; today: string; error?: string };

const guard = requireRole(['PATIENT']);

/**
 * The appointment to move (one of the patient's open ones; there is no single-appointment
 * endpoint, and a patient has at most five) and the free times, starting with its doctor and week.
 */
export async function rescheduleLoader(
  args: LoaderFunctionArgs,
): Promise<RescheduleData | Response> {
  const redirect = await guard(args);
  if (redirect instanceof Response) return redirect;
  const today = dateKey(new Date());
  let current: Appointment | undefined;
  try {
    const open = await fetchMyAppointments({ status: 'BOOKED', from: new Date() });
    current = open.find(({ id }) => id === args.params.id);
  } catch (error) {
    return { current: null, today, error: errorMessage(error) };
  }
  if (!current) return { current: null, today };
  const browser = await loadAvailability(new URL(args.request.url), {
    doctor: current.doctor.id,
    week: mondayOf(dateKey(new Date(current.startsAt))),
  });
  return { ...browser, current };
}

/** Moves the appointment (A30) in one step; the old time stays booked if anything fails. */
export async function rescheduleAction({
  request,
  params,
}: ActionFunctionArgs): Promise<TimeActionResult> {
  const form = await request.formData();
  const startsAt = String(form.get('startsAt') ?? '');
  const doctorId = String(form.get('doctorId') ?? '') || undefined;
  try {
    const { data, error } = await api.POST('/api/v1/appointments/{id}/reschedule', {
      params: { path: { id: params.id ?? '' } },
      body: { startsAt, doctorId },
    });
    if (data) return { appointment: data };
    return { error: errorMessage(error), conflict: isTimeConflict(error) };
  } catch {
    return { error: errorMessage(null) };
  }
}

export function ReschedulePage() {
  const data = useLoaderData<RescheduleData>();
  const settings = usePracticeSettings();
  const navigate = useNavigate();
  const [option, setOption] = useState<TimeOption | null>(null);
  const deadlineHours = settings?.cancellationDeadlineHours ?? null;

  if (!data.current) {
    return (
      <Flex direction="column" gap="6">
        <PatientPageHeader title="Termin verschieben" back>
          Wählen Sie eine neue Uhrzeit für Ihren Termin.
        </PatientPageHeader>
        {data.error ? (
          <Notice tone="error">{data.error}</Notice>
        ) : (
          <Card size="3">
            <Flex direction="column" gap="3" align="start">
              <Text as="p" size="3">
                Dieser Termin wurde nicht gefunden oder kann nicht mehr verschoben werden.
              </Text>
              <Button asChild variant="soft">
                <RouterLink to="/appointments">Zu meinen Terminen</RouterLink>
              </Button>
            </Flex>
          </Card>
        )}
      </Flex>
    );
  }

  const current = data.current;
  const deadline = deadlineHours === null ? null : changeDeadline(current.startsAt, deadlineHours);
  const locked = deadline !== null && Date.now() > deadline.getTime();

  return (
    <Flex direction="column" gap="6">
      <PatientPageHeader title="Termin verschieben" back>
        Wählen Sie eine neue Uhrzeit. Ihr bisheriger Termin bleibt bestehen, bis der neue bestätigt
        ist.
      </PatientPageHeader>

      <Flex direction="column" gap="2">
        <Text size="2" weight="medium" color="gray">
          Ihr aktueller Termin
        </Text>
        <AppointmentCard appointment={current} today={data.today} />
      </Flex>

      {data.error && <Notice tone="error">{data.error}</Notice>}

      {locked ? (
        <Callout.Root color="amber" highContrast>
          <Callout.Icon>
            <InfoIcon />
          </Callout.Icon>
          <Callout.Text>
            Dieser Termin beginnt in weniger als {deadlineHours} Stunden und kann online nicht mehr
            verschoben werden. Bitte wenden Sie sich an die Praxis.
          </Callout.Text>
        </Callout.Root>
      ) : (
        <AvailabilityBrowser data={data} onSelect={setOption} />
      )}

      {option && (
        <TimeDialog
          mode="reschedule"
          option={option}
          current={current}
          deadlineHours={deadlineHours}
          today={data.today}
          onClose={(done) => (done ? navigate('/appointments') : setOption(null))}
        />
      )}
    </Flex>
  );
}
