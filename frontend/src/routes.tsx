import { Flex, Spinner } from '@radix-ui/themes';
import type { RouteObject } from 'react-router';
import { guestOnly, mfaPending, requireRole, toHome } from './auth/guards';
import { loadSession } from './auth/session';
import { ErrorPage } from './pages/ErrorPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { PlaceholderPage } from './pages/PlaceholderPage';
import { RootLayout } from './pages/RootLayout';

export const routes: RouteObject[] = [
  {
    path: '/',
    loader: () => loadSession(),
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    hydrateFallbackElement: (
      <Flex justify="center" p="9">
        <Spinner size="3" />
      </Flex>
    ),
    children: [
      { index: true, loader: toHome },
      {
        path: 'login',
        loader: guestOnly,
        element: <PlaceholderPage title="Log in" ticket="#24" />,
      },
      {
        path: 'register',
        loader: guestOnly,
        element: <PlaceholderPage title="Register" ticket="#24" />,
      },
      {
        path: 'mfa',
        loader: mfaPending,
        element: <PlaceholderPage title="Two-factor authentication" ticket="#24" />,
      },
      {
        path: 'appointments',
        loader: requireRole(['PATIENT']),
        element: <PlaceholderPage title="My appointments" ticket="#25" />,
      },
      {
        path: 'staff',
        loader: requireRole(['STAFF', 'DOCTOR']),
        element: <PlaceholderPage title="Practice" ticket="#26" />,
      },
      {
        path: 'admin',
        loader: requireRole(['ADMIN']),
        element: <PlaceholderPage title="Administration" ticket="#26" />,
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];
