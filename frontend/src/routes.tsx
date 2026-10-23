import { Flex, Spinner } from '@radix-ui/themes';
import type { RouteObject } from 'react-router';
import { guestOnly, mfaPending, requireRole, toHome } from './auth/guards';
import { logoutAction } from './auth/logout';
import { loadSession } from './auth/session';
import { AppLayout } from './pages/AppLayout';
import { AuthLayout } from './pages/auth/AuthLayout';
import { LoginPage, loginAction } from './pages/auth/LoginPage';
import { MfaPage, mfaAction, mfaShouldRevalidate } from './pages/auth/MfaPage';
import { RegisterPage, registerAction } from './pages/auth/RegisterPage';
import { SetupPage, setupAction, setupLoader } from './pages/auth/SetupPage';
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
          {
            path: 'mfa',
            loader: mfaPending,
            action: mfaAction,
            shouldRevalidate: mfaShouldRevalidate,
            element: <MfaPage />,
          },
          { path: 'setup', loader: setupLoader, action: setupAction, element: <SetupPage /> },
        ],
      },
      // Form target only; a direct visit goes to the start page.
      { path: 'logout', loader: toHome, action: logoutAction },
      {
        element: <AppLayout />,
        children: [
          {
            path: 'appointments',
            loader: requireRole(['PATIENT']),
            element: <PlaceholderPage title="Meine Termine" ticket="#25" />,
          },
          {
            path: 'staff',
            loader: requireRole(['STAFF', 'DOCTOR']),
            element: <PlaceholderPage title="Praxis" ticket="#26" />,
          },
          {
            path: 'admin',
            loader: requireRole(['ADMIN']),
            element: <PlaceholderPage title="Verwaltung" ticket="#26" />,
          },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
];
