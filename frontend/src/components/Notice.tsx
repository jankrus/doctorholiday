import { Callout } from '@radix-ui/themes';
import type { ReactNode } from 'react';
import { AlertIcon, SuccessIcon } from './icons';

/**
 * Inline message that is part of the page content, e.g. a state the page shows. Transient
 * messages (the outcome of a submit) are toasts instead (`useToast()`, ui-design.md section 7).
 * Errors are announced immediately (`alert`), confirmations politely (`status`). High contrast
 * keeps the text readable on the tinted background.
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
