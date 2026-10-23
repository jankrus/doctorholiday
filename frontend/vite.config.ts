import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';
import { mockApi } from './dev-mock-api.ts';

// Dev server only: with API_PROXY_TARGET set (e.g. http://localhost:8080), /api is forwarded to that
// backend, so the browser sees a single origin as it does behind ingress-nginx. Without it, a mock
// answers /api (see dev-mock-api.ts). Neither is exposed to client code (no VITE_ prefix).
const apiProxyTarget = process.env.API_PROXY_TARGET;

export default defineConfig({
  plugins: [react(), ...(apiProxyTarget ? [] : [mockApi()])],
  server: {
    proxy: apiProxyTarget ? { '/api': apiProxyTarget } : undefined,
  },
  build: {
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    unstubGlobals: true,
  },
});
