import { Button, Flex, Link, Text, TextField } from '@radix-ui/themes';
import { useRef, useState } from 'react';
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
import {
  isPasswordLengthValid,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  passwordLength,
  validateRegistration,
  type FieldErrors,
  type RegistrationInput,
} from '../../auth/validation';
import { FormField, useFocusFirstError } from '../../components/FormField';
import { Notice } from '../../components/Notice';
import { PageHeader } from '../../components/PageHeader';
import { PasswordField } from '../../components/PasswordField';
import { Requirement } from '../../components/Requirement';

type RegisterResult = { fieldErrors?: FieldErrors<keyof RegistrationInput>; error?: string };

/** Checks the input locally, then registers. The server answers 202 whether or not the e-mail is taken (BR-02). */
export async function registerAction({
  request,
}: ActionFunctionArgs): Promise<RegisterResult | Response> {
  const form = await request.formData();
  const input: RegistrationInput = {
    displayName: String(form.get('displayName') ?? '').trim(),
    email: String(form.get('email') ?? '').trim(),
    password: String(form.get('password') ?? ''),
    confirmPassword: String(form.get('confirmPassword') ?? ''),
  };
  const fieldErrors = validateRegistration(input);
  if (fieldErrors) return { fieldErrors };

  try {
    const { response, error } = await api.POST('/api/v1/auth/register', {
      body: {
        email: input.email,
        password: input.password,
        displayName: input.displayName || undefined,
      },
    });
    if (response.ok) return redirect('/login?registered');
    return { error: errorMessage(error) };
  } catch {
    return { error: errorMessage(null) };
  }
}

export function RegisterPage() {
  const result = useActionData<RegisterResult>();
  const submitting = useNavigation().state === 'submitting';
  const formRef = useRef<HTMLFormElement>(null);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const errors = result?.fieldErrors ?? {};

  useFocusFirstError(formRef, result?.fieldErrors);

  const length = passwordLength(password);

  return (
    <Flex direction="column" gap="6">
      <PageHeader title="Konto erstellen">
        Mit einem Konto buchen und verwalten Sie Ihre Termine online. Mitarbeitende der Praxis
        erhalten stattdessen eine Einladung.
      </PageHeader>

      {result?.error && <Notice tone="error">{result.error}</Notice>}

      <Form method="post" noValidate ref={formRef}>
        <Flex direction="column" gap="5">
          <FormField
            label="Name"
            optional
            hint="So spricht die Praxis Sie an."
            error={errors.displayName}
          >
            {(control) => (
              <TextField.Root {...control} name="displayName" size="3" autoComplete="name" />
            )}
          </FormField>
          <FormField label="E-Mail-Adresse" error={errors.email}>
            {(control) => (
              <TextField.Root
                {...control}
                name="email"
                type="email"
                size="3"
                autoComplete="email"
                inputMode="email"
                spellCheck={false}
              />
            )}
          </FormField>
          <FormField
            label="Passwort"
            error={errors.password}
            hint={
              <Flex direction="column" gap="1">
                <Requirement met={isPasswordLengthValid(password)}>
                  {length > PASSWORD_MAX_LENGTH
                    ? `Höchstens ${PASSWORD_MAX_LENGTH} Zeichen`
                    : `Mindestens ${PASSWORD_MIN_LENGTH} Zeichen`}
                </Requirement>
                <Text as="p" size="2" color="gray">
                  Tipp: Einige zufällige Wörter ergeben ein starkes Passwort, das Sie sich leicht
                  merken können.
                </Text>
              </Flex>
            }
          >
            {(control) => (
              <PasswordField
                {...control}
                name="password"
                size="3"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            )}
          </FormField>
          <FormField
            label="Passwort wiederholen"
            error={errors.confirmPassword}
            hint={
              confirmPassword && (
                <Requirement met={confirmPassword === password}>
                  Passwörter stimmen überein
                </Requirement>
              )
            }
          >
            {(control) => (
              <PasswordField
                {...control}
                name="confirmPassword"
                size="3"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
              />
            )}
          </FormField>
          <Button type="submit" size="3" loading={submitting}>
            Konto erstellen
          </Button>
        </Flex>
      </Form>

      <Text as="p" size="2">
        <Text color="gray">Bereits registriert?</Text>{' '}
        <Link asChild weight="medium">
          <RouterLink to="/login">Anmelden</RouterLink>
        </Link>
      </Text>
    </Flex>
  );
}
