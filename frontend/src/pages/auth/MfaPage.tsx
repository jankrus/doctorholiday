import { Box, Button, Card, Checkbox, Flex, Text, TextField } from '@radix-ui/themes';
import { useEffect, useRef, useState, type Ref } from 'react';
import {
  Form,
  redirect,
  useActionData,
  useFetcher,
  useLoaderData,
  useNavigate,
  useNavigation,
  type ActionFunctionArgs,
  type ShouldRevalidateFunction,
} from 'react-router';
import { api, type MfaEnrollment, type SessionInfo } from '../../api/client';
import { errorMessage } from '../../api/errors';
import { homePath } from '../../auth/guards';
import {
  normalizeRecoveryCode,
  normalizeTotpCode,
  recoveryCodeError,
  totpCodeError,
} from '../../auth/validation';
import { CopyButton } from '../../components/CopyButton';
import { FormField, type FieldControlProps } from '../../components/FormField';
import { DownloadIcon } from '../../components/icons';
import { LogoutButton } from '../../components/LogoutButton';
import { Notice } from '../../components/Notice';
import { PageHeader } from '../../components/PageHeader';
import { QrCode } from '../../components/QrCode';
import './MfaPage.css';

type Mode = 'totp' | 'recovery';
type FormResult = { fieldError?: string; error?: string };
type ChallengeResult = FormResult & { mode: Mode };
type EnrollResult = { enrollment?: MfaEnrollment; error?: string };
type ConfirmResult = FormResult & { recoveryCodes?: string[]; session?: SessionInfo };

async function verify(body: { code: string } | { recoveryCode: string }) {
  try {
    const { data, error } = await api.POST('/api/v1/auth/mfa/verify', { body });
    return data ? { data } : { error: errorMessage(error) };
  } catch {
    return { error: errorMessage(null) };
  }
}

async function enroll(): Promise<EnrollResult> {
  try {
    const { data, error } = await api.POST('/api/v1/auth/mfa/enroll');
    return data ? { enrollment: data } : { error: errorMessage(error) };
  } catch {
    return { error: errorMessage(null) };
  }
}

/**
 * Three intents: `enroll` creates a TOTP secret, `confirm` enables MFA with the first code and
 * returns the recovery codes, anything else is the login challenge (TOTP or recovery code).
 */
export async function mfaAction({
  request,
}: ActionFunctionArgs): Promise<EnrollResult | ConfirmResult | ChallengeResult | Response> {
  const form = await request.formData();
  const intent = form.get('intent');
  const raw = String(form.get('code') ?? '');

  if (intent === 'enroll') return enroll();

  if (intent === 'confirm') {
    const code = normalizeTotpCode(raw);
    const fieldError = totpCodeError(code);
    if (fieldError) return { fieldError };
    const result = await verify({ code });
    if (!result.data) return { error: result.error };
    return { recoveryCodes: result.data.recoveryCodes ?? [], session: result.data.session };
  }

  const mode: Mode = form.get('mode') === 'recovery' ? 'recovery' : 'totp';
  const code = mode === 'totp' ? normalizeTotpCode(raw) : normalizeRecoveryCode(raw);
  const fieldError = mode === 'totp' ? totpCodeError(code) : recoveryCodeError(code);
  if (fieldError) return { mode, fieldError };
  const result = await verify(mode === 'totp' ? { code } : { recoveryCode: code });
  if (result.data) return redirect(homePath(result.data.session));
  return { mode, error: result.error };
}

/**
 * The step guard must not run again after an action on this page: confirming the enrolment makes
 * the session `ACTIVE`, and the guard would redirect before the recovery codes are shown.
 */
export const mfaShouldRevalidate: ShouldRevalidateFunction = () => false;

export function MfaPage() {
  const session = useLoaderData<SessionInfo>();
  return session.state === 'MFA_PENDING' ? <MfaChallenge /> : <MfaEnrollment />;
}

/** Clears and focuses the code input after a failed attempt, so the next code can be typed. */
function useResetOnError(result: FormResult | undefined) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if ((result?.error || result?.fieldError) && ref.current) {
      ref.current.value = '';
      ref.current.focus();
    }
  }, [result]);
  return ref;
}

function CodeInput({
  mode,
  inputRef,
  ...control
}: FieldControlProps & { mode: Mode; inputRef: Ref<HTMLInputElement> }) {
  const totp = mode === 'totp';
  return (
    <TextField.Root
      {...control}
      ref={inputRef}
      name="code"
      size="3"
      className="mfa-code-input"
      autoComplete="one-time-code"
      inputMode={totp ? 'numeric' : 'text'}
      placeholder={totp ? '123456' : 'xxxxx-xxxxx'}
      autoCapitalize="off"
      spellCheck={false}
      autoFocus
    />
  );
}

function MfaChallenge() {
  const result = useActionData<ChallengeResult>();
  const submitting = useNavigation().state === 'submitting';
  const [mode, setMode] = useState<Mode>('totp');
  const current = result?.mode === mode ? result : undefined;
  const inputRef = useResetOnError(current);

  return (
    <Flex direction="column" gap="6">
      <PageHeader title="Anmeldung bestätigen">
        {mode === 'totp'
          ? 'Geben Sie den 6-stelligen Code aus Ihrer Authenticator-App ein.'
          : 'Geben Sie einen Ihrer Wiederherstellungscodes ein. Jeder Code funktioniert nur einmal.'}
      </PageHeader>

      {current?.error && <Notice tone="error">{current.error}</Notice>}

      <Form method="post" noValidate key={mode}>
        <input type="hidden" name="mode" value={mode} />
        <Flex direction="column" gap="5">
          <FormField
            label={mode === 'totp' ? 'Bestätigungscode' : 'Wiederherstellungscode'}
            error={current?.fieldError}
          >
            {(control) => <CodeInput {...control} mode={mode} inputRef={inputRef} />}
          </FormField>
          <Button type="submit" size="3" loading={submitting}>
            Bestätigen
          </Button>
        </Flex>
      </Form>

      <Flex direction="column" gap="4" align="start">
        <Button
          type="button"
          variant="ghost"
          size="2"
          onClick={() => setMode(mode === 'totp' ? 'recovery' : 'totp')}
        >
          {mode === 'totp'
            ? 'Kein Zugriff auf die App? Wiederherstellungscode verwenden'
            : 'Stattdessen den Code aus der App verwenden'}
        </Button>
        <LogoutButton>Abbrechen und abmelden</LogoutButton>
      </Flex>
    </Flex>
  );
}

function MfaEnrollment() {
  const enroll = useFetcher<EnrollResult>();
  const confirm = useFetcher<ConfirmResult>();
  const inputRef = useResetOnError(confirm.data);
  const enrollment = enroll.data?.enrollment;

  if (confirm.data?.recoveryCodes && confirm.data.session) {
    return (
      <RecoveryCodes codes={confirm.data.recoveryCodes} next={homePath(confirm.data.session)} />
    );
  }

  if (!enrollment) {
    return (
      <Flex direction="column" gap="6">
        <PageHeader title="Zweiten Faktor einrichten">
          Konten des Praxisteams sind zusätzlich zum Passwort mit einem zweiten Faktor geschützt.
          Dafür brauchen Sie eine Authenticator-App auf Ihrem Smartphone. Die Einrichtung dauert
          etwa zwei Minuten.
        </PageHeader>
        {enroll.data?.error && <Notice tone="error">{enroll.data.error}</Notice>}
        <enroll.Form method="post">
          <input type="hidden" name="intent" value="enroll" />
          <Button type="submit" size="3" loading={enroll.state !== 'idle'} className="mfa-full">
            Einrichtung starten
          </Button>
        </enroll.Form>
        <Box>
          <LogoutButton>Abbrechen und abmelden</LogoutButton>
        </Box>
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap="6">
      <PageHeader title="Zweiten Faktor einrichten">
        Verbinden Sie Ihre Authenticator-App in drei Schritten mit Ihrem Konto.
      </PageHeader>

      <ol className="mfa-steps">
        <li>
          <Text as="p" size="3" weight="medium">
            App öffnen
          </Text>
          <Text as="p" size="2" color="gray">
            Öffnen Sie Ihre Authenticator-App und fügen Sie ein neues Konto hinzu.
          </Text>
        </li>
        <li>
          <Text as="p" size="3" weight="medium">
            QR-Code scannen
          </Text>
          <Flex direction="column" gap="3" mt="3">
            <Card size="2" className="mfa-qr">
              <QrCode value={enrollment.otpauthUri} label="QR-Code für die Authenticator-App" />
            </Card>
            <details className="mfa-secret">
              <summary>
                <Text size="2">Scannen nicht möglich? Schlüssel manuell eingeben</Text>
              </summary>
              <Flex direction="column" gap="3" align="start" mt="3">
                <Text as="p" size="2" color="gray">
                  Geben Sie diesen Schlüssel in der App ein (zeitbasiert, 6 Ziffern):
                </Text>
                <code className="mfa-secret__value">{groupSecret(enrollment.secret)}</code>
                <CopyButton text={enrollment.secret}>Schlüssel kopieren</CopyButton>
              </Flex>
            </details>
          </Flex>
        </li>
        <li>
          <Text as="p" size="3" weight="medium">
            Code eingeben
          </Text>
          <Box mt="3">
            {confirm.data?.error && (
              <Box mb="4">
                <Notice tone="error">{confirm.data.error}</Notice>
              </Box>
            )}
            <confirm.Form method="post" noValidate>
              <input type="hidden" name="intent" value="confirm" />
              <Flex direction="column" gap="5">
                <FormField
                  label="Bestätigungscode"
                  hint="Die App zeigt einen 6-stelligen Code, der sich alle 30 Sekunden ändert."
                  error={confirm.data?.fieldError}
                >
                  {(control) => <CodeInput {...control} mode="totp" inputRef={inputRef} />}
                </FormField>
                <Button type="submit" size="3" loading={confirm.state !== 'idle'}>
                  Bestätigen und aktivieren
                </Button>
              </Flex>
            </confirm.Form>
          </Box>
        </li>
      </ol>

      <Box>
        <LogoutButton>Abbrechen und abmelden</LogoutButton>
      </Box>
    </Flex>
  );
}

/** Base32 secret in groups of four, easier to type: `ABCD EFGH …`. */
function groupSecret(secret: string): string {
  return secret.replace(/(.{4})(?=.)/g, '$1 ');
}

function downloadCodes(codes: string[]) {
  const text = [
    'Doctor Holiday – Wiederherstellungscodes',
    'Jeder Code funktioniert nur einmal.',
    '',
    ...codes,
    '',
  ].join('\n');
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'doctor-holiday-wiederherstellungscodes.txt';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/**
 * Shown exactly once after the enrolment (BR-07). The codes live only in this component's state
 * and are gone once the user continues.
 */
function RecoveryCodes({ codes, next }: { codes: string[]; next: string }) {
  const navigate = useNavigate();
  const [saved, setSaved] = useState(false);

  return (
    <Flex direction="column" gap="6">
      <PageHeader title="Wiederherstellungscodes sichern">
        Falls Sie keinen Zugriff auf Ihre App haben, melden Sie sich mit einem dieser Codes an.
        Jeder Code funktioniert nur einmal. Die Codes werden nur jetzt angezeigt.
      </PageHeader>

      <Notice tone="success">Die Zwei-Faktor-Authentifizierung ist aktiv.</Notice>

      <Card size="3">
        <ol className="mfa-recovery-codes" aria-label="Wiederherstellungscodes">
          {codes.map((code) => (
            <li key={code}>
              <code>{code}</code>
            </li>
          ))}
        </ol>
        <Flex gap="3" mt="4" wrap="wrap">
          <CopyButton text={codes.join('\n')}>Codes kopieren</CopyButton>
          <Button type="button" variant="soft" size="2" onClick={() => downloadCodes(codes)}>
            <DownloadIcon />
            Herunterladen
          </Button>
        </Flex>
      </Card>

      <Text as="label" size="2">
        <Flex gap="2" align="start">
          <Checkbox
            size="2"
            checked={saved}
            onCheckedChange={(checked) => setSaved(checked === true)}
          />
          Ich habe die Codes sicher aufbewahrt, zum Beispiel im Passwort-Manager oder ausgedruckt.
        </Flex>
      </Text>

      <Button type="button" size="3" disabled={!saved} onClick={() => navigate(next)}>
        Weiter
      </Button>
    </Flex>
  );
}
