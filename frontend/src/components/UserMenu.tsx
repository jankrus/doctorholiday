import { Avatar, DropdownMenu, Flex, Spinner, Text } from '@radix-ui/themes';
import { useNavigation, useSubmit } from 'react-router';
import type { SessionInfo } from '../api/client';
import { ChevronDownIcon, LogoutIcon } from './icons';
import './UserMenu.css';

type User = NonNullable<SessionInfo['user']>;

export function initials(name: string | undefined, email: string): string {
  const words = (name ?? '').split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? [words[0], words[words.length - 1]] : [words[0] ?? email];
  return letters.map((word) => word?.charAt(0).toUpperCase() ?? '').join('');
}

/**
 * Account button in the app header (initials and name) that opens a menu with the account's
 * details and „Abmelden“. Logging out posts to the `/logout` route action like `LogoutButton`.
 */
export function UserMenu({ user }: { user: User }) {
  const submit = useSubmit();
  const navigation = useNavigation();
  const loggingOut = navigation.state !== 'idle' && navigation.formAction === '/logout';
  const name = user.displayName ?? user.email;
  const avatar = initials(user.displayName, user.email);

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        <button type="button" className="user-menu__trigger">
          <Avatar size="2" radius="full" variant="solid" fallback={avatar} aria-hidden="true" />
          {/* Hidden visually on phones, but always the button's accessible name. */}
          <span className="user-menu__name">{name}</span>
          <span className="user-menu__chevron" aria-hidden="true">
            {loggingOut ? <Spinner size="1" /> : <ChevronDownIcon />}
          </span>
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content align="end" sideOffset={6} className="user-menu__content">
        <Flex align="center" gap="3" px="3" pt="2" pb="3">
          <Avatar size="3" radius="full" variant="solid" fallback={avatar} aria-hidden="true" />
          <Flex direction="column" minWidth="0">
            {user.displayName && (
              <Text size="2" weight="bold" truncate>
                {user.displayName}
              </Text>
            )}
            <Text size="2" color="gray" truncate>
              {user.email}
            </Text>
          </Flex>
        </Flex>
        <DropdownMenu.Separator />
        <DropdownMenu.Item
          onSelect={() => submit(null, { method: 'post', action: '/logout' })}
          disabled={loggingOut}
        >
          <LogoutIcon />
          Abmelden
        </DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}
