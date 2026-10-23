import { Flex, Heading, Text } from '@radix-ui/themes';
import type { ReactNode } from 'react';

/** Title and intro at the top of a form page. */
export function PageHeader({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Flex direction="column" gap="2">
      <Heading as="h1" size="7">
        {title}
      </Heading>
      <Text as="p" size="3" color="gray">
        {children}
      </Text>
    </Flex>
  );
}
