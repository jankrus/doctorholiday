import { Theme } from '@radix-ui/themes';
import { render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { ToastProvider } from '../components/Toasts';
import { routes } from '../routes';

/** The providers `main.tsx` puts around the router. */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <Theme>
      <ToastProvider>{children}</ToastProvider>
    </Theme>
  );
}

type Router = ReturnType<typeof createMemoryRouter>;

export function renderRouter(router: Router): Router {
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return router;
}

/** Renders the app's real route table at `path`; stub `fetch` first (see `stubSession`). */
export function renderRoute(path: string): Router {
  return renderRouter(createMemoryRouter(routes, { initialEntries: [path] }));
}

/** The toast viewport, reachable with F8. */
export function toastRegion(): HTMLElement {
  return screen.getByRole('region', { name: 'Meldungen (F8)' });
}

/** Waits for the one visible toast. */
export function findToast(): Promise<HTMLElement> {
  return within(toastRegion()).findByRole('listitem');
}

export function queryToasts(): HTMLElement[] {
  return within(toastRegion()).queryAllByRole('listitem');
}
