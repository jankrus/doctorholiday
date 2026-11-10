import { Box, Button, Flex, Text, TextField } from '@radix-ui/themes';
import { useRef } from 'react';
import {
  Form,
  redirect,
  useActionData,
  useLoaderData,
  useNavigation,
  type ActionFunctionArgs,
  type LoaderFunctionArgs,
} from 'react-router';
import { api, type PracticeSettings } from '../../api/client';
import { errorMessage } from '../../api/errors';
import { setupPending } from '../../auth/guards';
import {
  validatePracticeSettings,
  type FieldErrors,
  type PracticeSettingsInput,
} from '../../auth/validation';
import { FormField, useFocusFirstError, type FieldControlProps } from '../../components/FormField';
import { LogoutButton } from '../../components/LogoutButton';
import { Notice } from '../../components/Notice';
import { PageHeader } from '../../components/PageHeader';

type SettingsDefaults = Pick<
  PracticeSettings,
  'practiceName' | 'cancellationDeadlineHours' | 'appointmentMinutes'
>;

// BR-18 seed values, used if the current settings cannot be loaded.
const DEFAULTS: SettingsDefaults = {
  practiceName: 'Doctor Holiday',
  cancellationDeadlineHours: 24,
  appointmentMinutes: 15,
};

/** Only for the admin with pending setup; prefills the form with the seeded settings. */
export async function setupLoader(args: LoaderFunctionArgs): Promise<SettingsDefaults | Response> {
  const guard = await setupPending(args);
  if (guard instanceof Response) return guard;
  try {
    const { data } = await api.GET('/api/v1/settings');
    if (data) return data;
  } catch {
    // Prefilling is a convenience; the defaults work as well.
  }
  return DEFAULTS;
}

type SetupResult = { fieldErrors?: FieldErrors<keyof PracticeSettingsInput>; error?: string };

/** Saves the settings; the first save completes the setup, and `/` forwards to the admin area. */
export async function setupAction({
  request,
}: ActionFunctionArgs): Promise<SetupResult | Response> {
  const form = await request.formData();
  const result = validatePracticeSettings({
    practiceName: String(form.get('practiceName') ?? '').trim(),
    cancellationDeadlineHours: String(form.get('cancellationDeadlineHours') ?? ''),
    appointmentMinutes: String(form.get('appointmentMinutes') ?? ''),
  });
  if ('errors' in result) return { fieldErrors: result.errors };

  try {
    const { data, error } = await api.PUT('/api/v1/settings', { body: result.value });
    // The index route reloads the session (`setupRequired` is gone now) and picks the start page.
    if (data) return redirect('/');
    return { error: errorMessage(error) };
  } catch {
    return { error: errorMessage(null) };
  }
}

export function SetupPage() {
  const defaults = useLoaderData<SettingsDefaults>();
  const result = useActionData<SetupResult>();
  const submitting = useNavigation().state === 'submitting';
  const formRef = useRef<HTMLFormElement>(null);
  const errors = result?.fieldErrors ?? {};
  useFocusFirstError(formRef, result?.fieldErrors);

  return (
    <Flex direction="column" gap="6">
      <PageHeader title="Praxis einrichten">
        Willkommen! Mit Ihrem Konto verwalten Sie diese Praxis. Legen Sie zuerst die
        Grundeinstellungen fest – Sie können sie später jederzeit in der Verwaltung ändern.
      </PageHeader>

      {result?.error && <Notice tone="error">{result.error}</Notice>}

      <Form method="post" noValidate ref={formRef}>
        <Flex direction="column" gap="5">
          <FormField
            label="Name der Praxis"
            hint="So erscheint die Praxis in der Anwendung."
            error={errors.practiceName}
          >
            {(control) => (
              <TextField.Root
                {...control}
                name="practiceName"
                size="3"
                autoComplete="organization"
                defaultValue={defaults.practiceName}
              />
            )}
          </FormField>
          <FormField
            label="Absagefrist"
            hint="Bis so viele Stunden vor Beginn können Patientinnen und Patienten einen Termin online absagen oder verschieben (0 bis 168 Stunden)."
            error={errors.cancellationDeadlineHours}
          >
            {(control) => (
              <NumberField
                {...control}
                name="cancellationDeadlineHours"
                unit="Stunden"
                min={0}
                max={168}
                defaultValue={defaults.cancellationDeadlineHours}
              />
            )}
          </FormField>
          <FormField
            label="Termindauer"
            hint="Länge eines Termins (5 bis 240 Minuten). Gilt nur für neue Termine; gebuchte Termine bleiben unverändert."
            error={errors.appointmentMinutes}
          >
            {(control) => (
              <NumberField
                {...control}
                name="appointmentMinutes"
                unit="Minuten"
                min={5}
                max={240}
                defaultValue={defaults.appointmentMinutes}
              />
            )}
          </FormField>
          <Button type="submit" size="3" loading={submitting}>
            Speichern und fortfahren
          </Button>
        </Flex>
      </Form>

      <Box>
        <LogoutButton />
      </Box>
    </Flex>
  );
}

/** Whole-number input with its unit shown inside the field; the hint names the unit for screen readers. */
function NumberField({
  unit,
  ...props
}: FieldControlProps & {
  name: string;
  unit: string;
  min: number;
  max: number;
  defaultValue: number;
}) {
  return (
    <TextField.Root {...props} type="number" step={1} inputMode="numeric" size="3">
      <TextField.Slot side="right">
        <Text size="2" color="gray" aria-hidden="true">
          {unit}
        </Text>
      </TextField.Slot>
    </TextField.Root>
  );
}
