import { Button, Flex, Link, Text, TextField } from '@radix-ui/themes';
import { useEffect, useRef } from 'react';
import {
  Form,
  Link as RouterLink,
  redirect,
  useActionData,
  useNavigation,
  type ActionFunctionArgs,
} from 'react-router';
import { api } from '../../api/client';
import { errorMessage } from '../../api/errors';
import { homePath } from '../../auth/guards';
import { FormField } from '../../components/FormField';
import { PageHeader } from '../../components/PageHeader';
import { PasswordField } from '../../components/PasswordField';
import { useErrorToast } from '../../components/Toasts';

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
  const passwordRef = useRef<HTMLInputElement>(null);
  useErrorToast(result);

  // After a failed attempt the e-mail stays, the password is cleared for the next try.
  useEffect(() => {
    if (result?.error && passwordRef.current) {
      passwordRef.current.value = '';
      passwordRef.current.focus();
    }
  }, [result]);

  return (
    <Flex direction="column" gap="6">
      <PageHeader title="Anmelden">
        Willkommen zurück. Melden Sie sich an, um Ihre Termine zu verwalten.
      </PageHeader>

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
