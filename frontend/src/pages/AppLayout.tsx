import { Box, Container, Flex, Heading, Separator, Text } from '@radix-ui/themes';
import { Outlet, useRouteLoaderData } from 'react-router';
import type { SessionInfo } from '../api/client';

/** Shell for the app pages: header with the signed-in account above the page content. */
export function AppLayout() {
  const session = useRouteLoaderData<SessionInfo | null>('root');

  return (
    <Flex direction="column" minHeight="100vh">
      <Box asChild px="5" py="3">
        <header>
          <Flex justify="between" align="center">
            <Heading as="h2" size="4">
              Doctor Holiday
            </Heading>
            {session?.user && (
              <Text size="2" color="gray">
                {session.user.email}
              </Text>
            )}
          </Flex>
        </header>
      </Box>
      <Separator size="4" />
      <Container size="3" px="5" py="6" asChild>
        <main>
          <Outlet />
        </main>
      </Container>
    </Flex>
  );
}
