import '@radix-ui/themes/styles.css';
import './global.css';
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
    <Theme accentColor="jade" grayColor="sage" radius="large">
      <RouterProvider router={router} />
    </Theme>
  </StrictMode>,
);
