import { Button } from '@radix-ui/themes';
import type { ReactNode } from 'react';
import { Form, useNavigation } from 'react-router';

/** Ends the session via the `/logout` route action. */
export function LogoutButton({ children = 'Abmelden' }: { children?: ReactNode }) {
  const navigation = useNavigation();
  const submitting = navigation.state !== 'idle' && navigation.formAction === '/logout';
  return (
    <Form method="post" action="/logout">
      <Button type="submit" variant="ghost" color="gray" size="2" loading={submitting}>
        {children}
      </Button>
    </Form>
  );
}
