import { Button, Callout, Flex, Heading, Link, Text, TextField } from '@radix-ui/themes';
import { useEffect, useRef } from 'react';
import {
  Form,
  Link as RouterLink,
  redirect,
  useActionData,
  useNavigation,
  useSearchParams,
  type ActionFunctionArgs,
} from 'react-router';
import { api } from '../../api/client';
import { errorMessage } from '../../api/errors';
import { homePath } from '../../auth/guards';
import { FormField } from '../../components/FormField';
import { AlertIcon, SuccessIcon } from '../../components/icons';
import { PasswordField } from '../../components/PasswordField';

type LoginResult = { error: string };

/** Sends the credentials; on success the session decides where to go (MFA, setup or home). */
export async function loginAction({
  request,
}: ActionFunctionArgs): Promise<LoginResult | Response> {
  const form = await request.formData();
  const email = String(form.get('email') ?? '').trim();
  const password = String(form.get('password') ?? '');
  if (!email || !password)
    return { error: 'Bitte geben Sie Ihre E-Mail-Adresse und Ihr Passwort ein.' };

  try {
    const { data, error } = await api.POST('/api/v1/auth/login', { body: { email, password } });
    if (data) return redirect(homePath(data));
    return { error: errorMessage(error) };
  } catch {
    return { error: errorMessage(null) };
  }
}

export function LoginPage() {
  const result = useActionData<LoginResult>();
  const submitting = useNavigation().state === 'submitting';
  const [params] = useSearchParams();
  const passwordRef = useRef<HTMLInputElement>(null);

  // After a failed attempt the e-mail stays, the password is cleared for the next try.
  useEffect(() => {
    if (result?.error && passwordRef.current) {
      passwordRef.current.value = '';
      passwordRef.current.focus();
    }
  }, [result]);

  return (
    <Flex direction="column" gap="6">
      <Flex direction="column" gap="2">
        <Heading as="h1" size="8">
          Anmelden
        </Heading>
        <Text as="p" size="3" color="gray">
          Willkommen zurück. Melden Sie sich an, um Ihre Termine zu verwalten.
        </Text>
      </Flex>

      {result?.error ? (
        <Callout.Root color="red" role="alert" highContrast>
          <Callout.Icon>
            <AlertIcon />
          </Callout.Icon>
          <Callout.Text>{result.error}</Callout.Text>
        </Callout.Root>
      ) : (
        params.has('registered') && (
          <Callout.Root role="status" highContrast>
            <Callout.Icon>
              <SuccessIcon />
            </Callout.Icon>
            <Callout.Text>
              Vielen Dank für Ihre Registrierung. Sie können sich jetzt anmelden.
            </Callout.Text>
          </Callout.Root>
        )
      )}

      <Form method="post" noValidate>
        <Flex direction="column" gap="5">
          <FormField label="E-Mail-Adresse">
            {(control) => (
              <TextField.Root
                {...control}
                name="email"
                type="email"
                size="3"
                autoComplete="username"
                inputMode="email"
                spellCheck={false}
                autoFocus
              />
            )}
          </FormField>
          <FormField label="Passwort">
            {(control) => (
              <PasswordField
                {...control}
                ref={passwordRef}
                name="password"
                size="3"
                autoComplete="current-password"
              />
            )}
          </FormField>
          <Button type="submit" size="3" loading={submitting}>
            Anmelden
          </Button>
        </Flex>
      </Form>

      <Flex direction="column" gap="2">
        <Text as="p" size="2">
          <Text color="gray">Noch kein Konto?</Text>{' '}
          <Link asChild weight="medium">
            <RouterLink to="/register">Jetzt registrieren</RouterLink>
          </Link>
        </Text>
        <Text as="p" size="2" color="gray">
          Passwort vergessen? Bitte wenden Sie sich an die Praxis.
        </Text>
      </Flex>
    </Flex>
  );
}
