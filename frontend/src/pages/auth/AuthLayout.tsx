import { Box, Flex, Text } from '@radix-ui/themes';
import type { ReactNode } from 'react';
import { Outlet } from 'react-router';
import { BrandMark } from '../../components/BrandMark';
import { CalendarIcon, ClockIcon, ShieldIcon } from '../../components/icons';
import './AuthLayout.css';

const HIGHLIGHTS: { icon: ReactNode; title: string; text: string }[] = [
  {
    icon: <CalendarIcon size={20} />,
    title: 'Book online, any time',
    text: 'Choose a free slot that suits you, without waiting on the phone.',
  },
  {
    icon: <ClockIcon size={20} />,
    title: 'Stay flexible',
    text: 'Move or cancel your appointment online up to the practice deadline.',
  },
  {
    icon: <ShieldIcon size={20} />,
    title: 'Protected access',
    text: 'Practice staff always log in with a second factor. You can add one too.',
  },
];

/**
 * Split screen for the steps before the app: a calm brand panel on the left, the form on the
 * right. On narrow screens the panel shrinks to a header and the form comes first.
 */
export function AuthLayout() {
  return (
    <div className="auth-layout">
      <aside className="auth-layout__brand">
        <BrandMark size="large" />
        <Flex direction="column" gap="6" className="auth-layout__intro">
          <Text as="p" size="8" weight="bold" className="auth-layout__claim">
            Your practice, just a few clicks away.
          </Text>
          <Flex asChild direction="column" gap="5">
            <ul className="auth-layout__highlights">
              {HIGHLIGHTS.map(({ icon, title, text }) => (
                <Flex asChild gap="3" key={title}>
                  <li>
                    <span className="auth-layout__highlight-icon">{icon}</span>
                    <Box>
                      <Text as="p" size="3" weight="medium" className="auth-layout__ink">
                        {title}
                      </Text>
                      <Text as="p" size="2" className="auth-layout__muted">
                        {text}
                      </Text>
                    </Box>
                  </li>
                </Flex>
              ))}
            </ul>
          </Flex>
        </Flex>
      </aside>
      <main className="auth-layout__main">
        <div className="auth-layout__form">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
