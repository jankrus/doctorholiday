import '@radix-ui/themes/styles.css';
import { Theme } from '@radix-ui/themes';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';
import { routes } from './routes';

const container = document.getElementById('root');
if (!container) throw new Error('Missing #root element');

const router = createBrowserRouter(routes);

createRoot(container).render(
  <StrictMode>
    <Theme accentColor="teal" grayColor="slate" radius="medium">
      <RouterProvider router={router} />
    </Theme>
  </StrictMode>,
);
