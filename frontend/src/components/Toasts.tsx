import * as RadixToast from '@radix-ui/react-toast';
import { Callout, IconButton } from '@radix-ui/themes';
import { createContext, useContext, useEffect, useSyncExternalStore, type ReactNode } from 'react';
import { useFetchers, useNavigation } from 'react-router';
import { AlertIcon, CloseIcon, SuccessIcon } from './icons';
import { getToasts, subscribeToasts, toast, type Toast, type ToastItem } from './toastStore';
import './Toasts.css';

/** Confirmations close after this long; Radix pauses the timer while the toasts are hovered or focused. */
export const SUCCESS_DURATION_MS = 5000;

const ToastContext = createContext<Toast | null>(null);

/**
 * Mounted once around the router, so toasts survive navigation. Renders the queue from
 * `toastStore` into one fixed viewport (docs/architecture/ui-design.md, section 7, "Toast").
 * F8 moves the focus to the toasts, Escape closes the focused one.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const items = useSyncExternalStore(subscribeToasts, getToasts);
  return (
    <ToastContext.Provider value={toast}>
      <RadixToast.Provider label="Meldung" duration={SUCCESS_DURATION_MS} swipeDirection="right">
        {children}
        {items.map((item) => (
          <ToastMessage key={item.id} item={item} />
        ))}
        <RadixToast.Viewport className="toast-viewport" label="Meldungen ({hotkey})" />
      </RadixToast.Provider>
    </ToastContext.Provider>
  );
}

/**
 * Errors are announced assertively (`foreground`) and stay; confirmations politely (`background`)
 * and close by themselves. Same colours, icon and `highContrast` as an inline callout.
 */
function ToastMessage({ item }: { item: ToastItem }) {
  const error = item.tone === 'error';
  return (
    <RadixToast.Root
      className="toast"
      type={error ? 'foreground' : 'background'}
      duration={error ? Infinity : undefined}
      onOpenChange={(open) => {
        if (!open) toast.dismiss(item.id);
      }}
    >
      <Callout.Root color={error ? 'red' : undefined} highContrast className="toast__callout">
        <Callout.Icon className="toast__icon">
          {error ? <AlertIcon /> : <SuccessIcon />}
        </Callout.Icon>
        <RadixToast.Description asChild>
          <Callout.Text className="toast__text">{item.text}</Callout.Text>
        </RadixToast.Description>
        <RadixToast.Close asChild>
          <IconButton
            variant="ghost"
            size="2"
            color={error ? 'red' : undefined}
            highContrast
            className="toast__close"
            aria-label="Meldung schließen"
          >
            <CloseIcon />
          </IconButton>
        </RadixToast.Close>
      </Callout.Root>
    </RadixToast.Root>
  );
}

/** The only way for components to raise a message: `toast.success(text)`, `toast.error(text)`. */
export function useToast(): Toast {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast() needs a <ToastProvider> above it.');
  return context;
}

/** Shows `result.error` as an error toast each time an action or fetcher returns a new result with one. */
export function useErrorToast(result: { error?: string } | undefined) {
  const toast = useToast();
  useEffect(() => {
    if (result?.error) toast.error(result.error);
  }, [result, toast]);
}

/**
 * Mounted in the root route: an error belongs to the attempt that caused it, so it goes away when
 * the user submits again (form or fetcher) or follows a link to another page. The redirect after a
 * submit keeps the toasts its action raised, e.g. the confirmation after logging out.
 */
export function ToastRouteSync() {
  const toast = useToast();
  const navigation = useNavigation();
  const fetchers = useFetchers();
  const submitting =
    navigation.state === 'submitting' || fetchers.some((fetcher) => fetcher.state === 'submitting');
  const leaving = navigation.state === 'loading' && !navigation.formMethod;

  useEffect(() => {
    if (submitting || leaving) toast.dismissErrors();
  }, [submitting, leaving, toast]);
  return null;
}
