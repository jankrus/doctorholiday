import { Flex, Heading, Link, Text } from '@radix-ui/themes';
import type { ReactNode } from 'react';
import { Link as RouterLink } from 'react-router';
import { ArrowLeftIcon } from '../../components/icons';
import './PatientPageHeader.css';

type Props = {
  title: string;
  /** Shows a link back to the appointment overview above the title. */
  back?: boolean;
  /** The page's primary action, next to the title on wide screens. */
  action?: ReactNode;
  children: ReactNode;
};

/** Title, intro and optional primary action at the top of a patient page. */
export function PatientPageHeader({ title, back, action, children }: Props) {
  return (
    <Flex direction="column" gap="3">
      {back && (
        <Link asChild size="2" weight="medium" className="patient-page__back">
          <RouterLink to="/appointments">
            <ArrowLeftIcon />
            Meine Termine
          </RouterLink>
        </Link>
      )}
      <Flex
        direction={{ initial: 'column', sm: 'row' }}
        justify="between"
        align={{ initial: 'stretch', sm: 'end' }}
        gap="4"
      >
        <Flex direction="column" gap="2">
          <Heading as="h1" size={{ initial: '7', sm: '8' }} className="patient-page__title">
            {title}
          </Heading>
          <Text as="p" size="3" color="gray">
            {children}
          </Text>
        </Flex>
        {action}
      </Flex>
    </Flex>
  );
}
