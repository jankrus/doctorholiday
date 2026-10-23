import { Button, Callout, Container, Flex } from '@radix-ui/themes';
import { GENERIC_ERROR_MESSAGE } from '../api/errors';

/** Fallback for any error thrown while loading or rendering a route; never shows its details. */
export function ErrorPage() {
  return (
    <Container size="2" p="6">
      <Flex direction="column" gap="4" align="start">
        <Callout.Root color="red" role="alert">
          <Callout.Text>{GENERIC_ERROR_MESSAGE}</Callout.Text>
        </Callout.Root>
        <Button asChild variant="soft">
          <a href="/">Back to start</a>
        </Button>
      </Flex>
    </Container>
  );
}
