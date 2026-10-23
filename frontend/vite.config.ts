import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Dev server only: forwards /api to a locally running backend, so the browser sees a single
// origin as it does behind ingress-nginx. Not exposed to client code (no VITE_ prefix).
const apiProxyTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8080';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': apiProxyTarget,
    },
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
