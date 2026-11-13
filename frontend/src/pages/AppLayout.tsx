import { Avatar, Container, Flex, Separator, TabNav, Text } from '@radix-ui/themes';
import {
  Link as RouterLink,
  Outlet,
  useLocation,
  useRouteLoaderData,
  type LoaderFunction,
} from 'react-router';
import { api, type PracticeSettings, type Role, type SessionInfo } from '../api/client';
import { loadSession } from '../auth/session';
import { BrandMark } from '../components/BrandMark';
import { LogoutButton } from '../components/LogoutButton';
import './AppLayout.css';

export type AppData = { settings: PracticeSettings | null };

/**
 * Practice settings for every app page (name, cancellation deadline, appointment length; A26).
 * Pages still render without them, so a failed request only hides details.
 */
export const appLayoutLoader: LoaderFunction = async (): Promise<AppData> => {
  const session = await loadSession();
  if (session?.state !== 'ACTIVE') return { settings: null };
  try {
    const { data } = await api.GET('/api/v1/settings');
    return { settings: data ?? null };
  } catch {
    return { settings: null };
  }
};

/** Settings loaded by the app layout, or `null` if they could not be loaded. */
export function usePracticeSettings(): PracticeSettings | null {
  return useRouteLoaderData<AppData>('app')?.settings ?? null;
}

type NavItem = { to: string; label: string; matches: (path: string) => boolean };

const NAV_BY_ROLE: Record<Role, NavItem[]> = {
  PATIENT: [
    {
      to: '/appointments',
      label: 'Meine Termine',
      matches: (path) => path.startsWith('/appointments') && path !== '/appointments/book',
    },
    {
      to: '/appointments/book',
      label: 'Termin buchen',
      matches: (path) => path === '/appointments/book',
    },
  ],
  STAFF: [{ to: '/staff', label: 'Praxis', matches: (path) => path.startsWith('/staff') }],
  DOCTOR: [{ to: '/staff', label: 'Praxis', matches: (path) => path.startsWith('/staff') }],
  ADMIN: [{ to: '/admin', label: 'Verwaltung', matches: (path) => path.startsWith('/admin') }],
};

function initials(name: string | undefined, email: string): string {
  const words = (name ?? '').split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? [words[0], words[words.length - 1]] : [words[0] ?? email];
  return letters.map((word) => word?.charAt(0).toUpperCase() ?? '').join('');
}

/** Shell for the app pages: brand, account and logout, the role's navigation, then the page. */
export function AppLayout() {
  const session = useRouteLoaderData<SessionInfo | null>('root');
  const settings = usePracticeSettings();
  const { pathname } = useLocation();
  const user = session?.state === 'ACTIVE' ? session.user : undefined;
  const nav = user ? NAV_BY_ROLE[user.role] : [];
  const practiceName = settings?.practiceName;

  return (
    <div className="app-layout">
      <header className="app-header">
        <Container size="3" px={{ initial: '4', sm: '5' }}>
          <Flex justify="between" align="center" gap="4" py="3">
            <Flex align="center" gap="4" minWidth="0">
              <RouterLink to="/" className="app-header__home" aria-label="Zur Startseite">
                <BrandMark />
              </RouterLink>
              {practiceName && practiceName !== 'Doctor Holiday' && (
                <Flex align="center" gap="4" className="app-header__practice" minWidth="0">
                  <Separator orientation="vertical" size="2" />
                  <Text size="2" color="gray" truncate>
                    {practiceName}
                  </Text>
                </Flex>
              )}
            </Flex>
            {user && (
              <Flex align="center" gap="3" flexShrink="0">
                <Avatar
                  size="2"
                  radius="full"
                  variant="soft"
                  fallback={initials(user.displayName, user.email)}
                  aria-hidden="true"
                />
                <Text size="2" className="app-header__account" truncate>
                  {user.displayName ?? user.email}
                </Text>
                <LogoutButton />
              </Flex>
            )}
          </Flex>
          {nav.length > 1 && (
            <TabNav.Root aria-label="Hauptnavigation" className="app-header__nav">
              {nav.map((item) => (
                <TabNav.Link key={item.to} asChild active={item.matches(pathname)}>
                  <RouterLink to={item.to}>{item.label}</RouterLink>
                </TabNav.Link>
              ))}
            </TabNav.Root>
          )}
        </Container>
      </header>
      <Container size="3" px={{ initial: '4', sm: '5' }} py={{ initial: '5', sm: '7' }} asChild>
        <main>
          <Outlet />
        </main>
      </Container>
    </div>
  );
}
