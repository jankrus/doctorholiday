import { Flex, Spinner } from '@radix-ui/themes';
import type { RouteObject } from 'react-router';
import { guestOnly, mfaPending, requireRole, setupPending, toHome } from './auth/guards';
import { loadSession } from './auth/session';
import { AppLayout } from './pages/AppLayout';
import { AuthLayout } from './pages/auth/AuthLayout';
import { LoginPage, loginAction } from './pages/auth/LoginPage';
import { RegisterPage, registerAction } from './pages/auth/RegisterPage';
import { ErrorPage } from './pages/ErrorPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { PlaceholderPage } from './pages/PlaceholderPage';

export const routes: RouteObject[] = [
  {
    id: 'root',
    path: '/',
    loader: () => loadSession(),
    errorElement: <ErrorPage />,
    hydrateFallbackElement: (
      <Flex justify="center" p="9">
        <Spinner size="3" />
      </Flex>
    ),
    children: [
      { index: true, loader: toHome },
      {
        element: <AuthLayout />,
        children: [
          { path: 'login', loader: guestOnly, action: loginAction, element: <LoginPage /> },
          {
            path: 'register',
            loader: guestOnly,
            action: registerAction,
            element: <RegisterPage />,
          },
        ],
      },
      {
        element: <AppLayout />,
        children: [
          {
            path: 'mfa',
            loader: mfaPending,
            element: <PlaceholderPage title="Two-factor authentication" ticket="#24" />,
          },
          {
            path: 'setup',
            loader: setupPending,
            element: <PlaceholderPage title="Practice setup" ticket="#24" />,
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
    ],
  },
];
