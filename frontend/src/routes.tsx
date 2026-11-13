import { Flex, Spinner } from '@radix-ui/themes';
import type { RouteObject } from 'react-router';
import { guestOnly, mfaPending, requireRole, toHome } from './auth/guards';
import { logoutAction } from './auth/logout';
import { loadSession } from './auth/session';
import { AppLayout, appLayoutLoader } from './pages/AppLayout';
import { AuthLayout } from './pages/auth/AuthLayout';
import { LoginPage, loginAction } from './pages/auth/LoginPage';
import { MfaPage, mfaAction, mfaShouldRevalidate } from './pages/auth/MfaPage';
import { RegisterPage, registerAction } from './pages/auth/RegisterPage';
import { SetupPage, setupAction, setupLoader } from './pages/auth/SetupPage';
import { ErrorPage } from './pages/ErrorPage';
import { NotFoundPage } from './pages/NotFoundPage';
import {
  AppointmentsPage,
  appointmentsAction,
  appointmentsLoader,
} from './pages/patient/AppointmentsPage';
import { BookPage, bookAction, bookLoader } from './pages/patient/BookPage';
import { ReschedulePage, rescheduleAction, rescheduleLoader } from './pages/patient/ReschedulePage';
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
        id: 'app',
        element: <AppLayout />,
        loader: appLayoutLoader,
        // Settings rarely change: reload them after a form submission or on another page, not
        // when only the query (week, doctor filter) changes.
        shouldRevalidate: ({ currentUrl, nextUrl, formMethod }) =>
          formMethod !== undefined || currentUrl.pathname !== nextUrl.pathname,
        children: [
          {
            path: 'appointments',
            loader: appointmentsLoader,
            action: appointmentsAction,
            element: <AppointmentsPage />,
          },
          {
            path: 'appointments/book',
            loader: bookLoader,
            action: bookAction,
            element: <BookPage />,
          },
          {
            path: 'appointments/:id/reschedule',
            loader: rescheduleLoader,
            action: rescheduleAction,
            element: <ReschedulePage />,
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
