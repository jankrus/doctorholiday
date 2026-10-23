import { Card, Heading, Link, Text } from '@radix-ui/themes';
import { Link as RouterLink } from 'react-router';

export function NotFoundPage() {
  return (
    <Card size="3">
      <Heading as="h1" size="6" mb="2">
        Seite nicht gefunden
      </Heading>
      <Text as="p">
        <Link asChild>
          <RouterLink to="/">Zur Startseite</RouterLink>
        </Link>
      </Text>
    </Card>
  );
}
