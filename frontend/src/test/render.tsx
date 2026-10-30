import { Theme } from '@radix-ui/themes';
import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { routes } from '../routes';

/** Renders the app's real route table at `path`; stub `fetch` first (see `stubSession`). */
export function renderRoute(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <Theme>
      <RouterProvider router={router} />
    </Theme>,
  );
  return router;
}
