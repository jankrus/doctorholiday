import { Callout } from '@radix-ui/themes';
import type { ReactNode } from 'react';
import { AlertIcon, SuccessIcon } from './icons';

/**
 * Page-level message above a form. Errors are announced immediately (`alert`), confirmations
 * politely (`status`). High contrast keeps the text readable on the tinted background.
 */
export function Notice({ tone, children }: { tone: 'error' | 'success'; children: ReactNode }) {
  const error = tone === 'error';
  return (
    <Callout.Root color={error ? 'red' : undefined} role={error ? 'alert' : 'status'} highContrast>
      <Callout.Icon>{error ? <AlertIcon /> : <SuccessIcon />}</Callout.Icon>
      <Callout.Text>{children}</Callout.Text>
    </Callout.Root>
  );
}
