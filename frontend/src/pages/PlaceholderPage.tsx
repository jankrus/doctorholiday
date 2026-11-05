import { Card, Heading, Text } from '@radix-ui/themes';

/** Stand-in for screens that later tickets build. */
export function PlaceholderPage({ title, ticket }: { title: string; ticket: string }) {
  return (
    <Card size="3">
      <Heading as="h1" size="6" mb="2">
        {title}
      </Heading>
      <Text as="p" color="gray">
        Diese Seite wird in {ticket} umgesetzt.
      </Text>
    </Card>
  );
}
