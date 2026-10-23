import { Card, Heading, Link, Text } from '@radix-ui/themes';
import { Link as RouterLink } from 'react-router';

export function NotFoundPage() {
  return (
    <Card size="3">
      <Heading as="h1" size="6" mb="2">
        Page not found
      </Heading>
      <Text as="p" color="gray">
        <Link asChild>
          <RouterLink to="/">Back to start</RouterLink>
        </Link>
      </Text>
    </Card>
  );
}
