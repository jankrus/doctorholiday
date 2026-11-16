/**
 * App-wide queue of transient messages, rendered as toasts by `ToastProvider`
 * (docs/architecture/ui-design.md, section 7, "Toast").
 *
 * Components raise messages with `useToast()`. Route actions run outside React; one that ends in a
 * redirect calls `toast` directly before redirecting, so the confirmation shows on the next page
 * without a flag in the URL. The queue lives in memory only: a reload starts empty.
 *
 * Texts are plain strings and React renders them as text. Error texts come from the fixed map in
 * `api/errors.ts`. Never put credentials, codes, recovery codes or MFA secrets into a toast.
 */

export type ToastTone = 'success' | 'error';
export type ToastItem = { id: number; tone: ToastTone; text: string };

/** At most this many toasts are visible; a new one pushes out the oldest. */
export const MAX_TOASTS = 3;

let items: readonly ToastItem[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function update(next: readonly ToastItem[]) {
  items = next.slice(-MAX_TOASTS);
  listeners.forEach((listener) => listener());
}

export const toast = {
  /** Confirmation: closes by itself after a few seconds. */
  success(text: string) {
    update([...items, { id: nextId++, tone: 'success', text }]);
  },
  /** Error: stays until closed or the next submit; replaces an earlier error instead of stacking. */
  error(text: string) {
    update([
      ...items.filter((item) => item.tone !== 'error'),
      { id: nextId++, tone: 'error', text },
    ]);
  },
  dismiss(id: number) {
    if (items.some((item) => item.id === id)) update(items.filter((item) => item.id !== id));
  },
  /** Called when the user submits again or leaves the page; confirmations stay. */
  dismissErrors() {
    if (items.some((item) => item.tone === 'error')) {
      update(items.filter((item) => item.tone !== 'error'));
    }
  },
  clear() {
    if (items.length) update([]);
  },
};

export type Toast = typeof toast;

export function subscribeToasts(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getToasts(): readonly ToastItem[] {
  return items;
}
