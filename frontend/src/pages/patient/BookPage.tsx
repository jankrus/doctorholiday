import { Callout, Flex } from '@radix-ui/themes';
import { useState } from 'react';
import { useLoaderData, type ActionFunctionArgs, type LoaderFunctionArgs } from 'react-router';
import { api } from '../../api/client';
import { errorMessage, isTimeConflict } from '../../api/errors';
import { fetchMyAppointments } from '../../appointments/api';
import { loadAvailability, type BrowserData } from '../../appointments/availability';
import { isReason } from '../../appointments/reasons';
import { requireRole } from '../../auth/guards';
import {
  AvailabilityBrowser,
  type TimeOption,
} from '../../components/appointments/AvailabilityBrowser';
import { TimeDialog, type TimeActionResult } from '../../components/appointments/TimeDialog';
import { InfoIcon } from '../../components/icons';
import { Notice } from '../../components/Notice';
import { usePracticeSettings } from '../AppLayout';
import { PatientPageHeader } from './PatientPageHeader';

/** BR-09: at most five open appointments per patient. */
export const OPEN_APPOINTMENT_LIMIT = 5;

type BookData = BrowserData & { limitReached: boolean };

const guard = requireRole(['PATIENT']);

export async function bookLoader(args: LoaderFunctionArgs): Promise<BookData | Response> {
  const redirect = await guard(args);
  if (redirect instanceof Response) return redirect;
  const [browser, open] = await Promise.all([
    loadAvailability(new URL(args.request.url)),
    // Only for an early hint; the server enforces the limit.
    fetchMyAppointments({ status: 'BOOKED', from: new Date() }).catch(() => []),
  ]);
  return { ...browser, limitReached: open.length >= OPEN_APPOINTMENT_LIMIT };
}

/** Books the chosen time (A08). A patient books for themselves: no patient or guest fields. */
export async function bookAction({ request }: ActionFunctionArgs): Promise<TimeActionResult> {
  const form = await request.formData();
  const doctorId = String(form.get('doctorId') ?? '');
  const startsAt = String(form.get('startsAt') ?? '');
  const reason = form.get('reason');
  if (!isReason(reason)) {
    const message = 'Bitte wählen Sie den Grund Ihres Termins.';
    return { error: message, fieldError: message };
  }
  try {
    const { data, error } = await api.POST('/api/v1/appointments', {
      body: { doctorId, startsAt, reason },
    });
    if (data) return { appointment: data };
    return { error: errorMessage(error), conflict: isTimeConflict(error) };
  } catch {
    return { error: errorMessage(null) };
  }
}

export function BookPage() {
  const data = useLoaderData<BookData>();
  const settings = usePracticeSettings();
  const [option, setOption] = useState<TimeOption | null>(null);

  return (
    <Flex direction="column" gap="6">
      <PatientPageHeader title="Termin buchen" back>
        Wählen Sie einen Tag und eine freie Uhrzeit.
        {settings && ` Ein Termin dauert ${settings.appointmentMinutes} Minuten.`}
      </PatientPageHeader>

      {data.error && <Notice tone="error">{data.error}</Notice>}
      {data.limitReached && (
        <Callout.Root color="amber" highContrast>
          <Callout.Icon>
            <InfoIcon />
          </Callout.Icon>
          <Callout.Text>
            Sie haben bereits {OPEN_APPOINTMENT_LIMIT} offene Termine, mehr sind nicht möglich.
            Bitte sagen Sie zuerst einen Termin ab, wenn Sie einen neuen brauchen.
          </Callout.Text>
        </Callout.Root>
      )}

      <AvailabilityBrowser data={data} onSelect={setOption} />

      {option && (
        <TimeDialog
          mode="book"
          option={option}
          deadlineHours={settings?.cancellationDeadlineHours ?? null}
          today={data.today}
          onClose={() => setOption(null)}
        />
      )}
    </Flex>
  );
}
