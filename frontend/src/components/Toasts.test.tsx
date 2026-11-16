import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppProviders, findToast, queryToasts, toastRegion } from '../test/render';
import { SUCCESS_DURATION_MS, useToast } from './Toasts';
import type { Toast } from './toastStore';

function renderToasts(): Toast {
  let toast: Toast | undefined;
  function Harness() {
    toast = useToast();
    return <button type="button">Seite</button>;
  }
  render(
    <AppProviders>
      <Harness />
    </AppProviders>,
  );
  if (!toast) throw new Error('Harness did not render');
  return toast;
}

const texts = () => queryToasts().map((item) => item.textContent);

afterEach(() => {
  vi.useRealTimers();
});

describe('useToast', () => {
  it('shows a confirmation and announces it politely', async () => {
    const toast = renderToasts();
    act(() => toast.success('Gespeichert.'));

    expect(await findToast()).toHaveTextContent('Gespeichert.');
    const announcement = await screen.findByRole('status');
    expect(announcement).toHaveAttribute('aria-live', 'polite');
    await waitFor(() => expect(announcement).toHaveTextContent('Meldung Gespeichert.'));
  });

  it('shows an error and announces it assertively', async () => {
    const toast = renderToasts();
    act(() => toast.error('Etwas ist schiefgelaufen.'));

    expect(await findToast()).toHaveTextContent('Etwas ist schiefgelaufen.');
    const announcement = await screen.findByRole('status');
    expect(announcement).toHaveAttribute('aria-live', 'assertive');
    await waitFor(() => expect(announcement).toHaveTextContent('Etwas ist schiefgelaufen.'));
    // The close button's label is not read out as part of the message.
    expect(announcement).not.toHaveTextContent('schließen');
  });

  it('replaces an earlier error instead of stacking it', () => {
    const toast = renderToasts();
    act(() => {
      toast.success('Gespeichert.');
      toast.error('Erster Fehler.');
      toast.error('Zweiter Fehler.');
    });

    expect(texts()).toEqual(['Gespeichert.', 'Zweiter Fehler.']);
  });

  it('shows at most three toasts and drops the oldest', () => {
    const toast = renderToasts();
    act(() => {
      for (const n of [1, 2, 3, 4]) toast.success(`Meldung ${n}.`);
    });

    expect(texts()).toEqual(['Meldung 2.', 'Meldung 3.', 'Meldung 4.']);
  });

  it('closes confirmations after a few seconds, errors not', () => {
    vi.useFakeTimers();
    const toast = renderToasts();
    act(() => {
      toast.success('Gespeichert.');
      toast.error('Fehler.');
    });

    act(() => vi.advanceTimersByTime(SUCCESS_DURATION_MS - 100));
    expect(texts()).toEqual(['Gespeichert.', 'Fehler.']);
    act(() => vi.advanceTimersByTime(200));
    expect(texts()).toEqual(['Fehler.']);
    act(() => vi.advanceTimersByTime(60_000));
    expect(texts()).toEqual(['Fehler.']);
  });

  it('pauses the timer while a toast has the focus', () => {
    vi.useFakeTimers();
    const toast = renderToasts();
    act(() => toast.success('Gespeichert.'));

    act(() => screen.getByRole('button', { name: 'Meldung schließen' }).focus());
    act(() => vi.advanceTimersByTime(SUCCESS_DURATION_MS * 3));
    expect(texts()).toEqual(['Gespeichert.']);

    act(() => screen.getByRole('button', { name: 'Seite' }).focus());
    act(() => vi.advanceTimersByTime(SUCCESS_DURATION_MS + 100));
    expect(texts()).toEqual([]);
  });

  it('closes a toast with its close button', async () => {
    const toast = renderToasts();
    act(() => toast.error('Fehler.'));

    await userEvent.click(screen.getByRole('button', { name: 'Meldung schließen' }));
    expect(texts()).toEqual([]);
  });

  it('is reached with F8 and closed with Escape', async () => {
    const toast = renderToasts();
    act(() => toast.error('Fehler.'));

    fireEvent.keyDown(document, { key: 'F8', code: 'F8' });
    expect(within(toastRegion()).getByRole('list')).toHaveFocus();
    await userEvent.tab();
    expect(await findToast()).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    expect(texts()).toEqual([]);
  });

  it('renders texts as plain text', async () => {
    const toast = renderToasts();
    act(() => toast.error('<img src=x onerror=alert(1)>'));

    expect(await findToast()).toHaveTextContent('<img src=x onerror=alert(1)>');
    expect(toastRegion().querySelector('img')).toBeNull();
  });

  it('dismisses errors on request and keeps confirmations', () => {
    const toast = renderToasts();
    act(() => {
      toast.success('Gespeichert.');
      toast.error('Fehler.');
      toast.dismissErrors();
    });

    expect(texts()).toEqual(['Gespeichert.']);
  });

  it('needs the provider', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    function Orphan() {
      useToast();
      return null;
    }
    expect(() => render(<Orphan />)).toThrow('useToast() needs a <ToastProvider> above it.');
  });
});
