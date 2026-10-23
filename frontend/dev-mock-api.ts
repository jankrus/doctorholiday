import type { ServerResponse } from 'node:http';
import type { Plugin } from 'vite';

// Dev server only (`apply: 'serve'`, never part of the build): answers /api while no backend runs,
// so the pages can be viewed. The frontend code is unchanged and talks to it like to the backend.
// Pick the session with http://localhost:5173/__mock/session?as=<one of SESSIONS>.

const active = (role: string) => ({
  state: 'ACTIVE',
  user: {
    id: '00000000-0000-4000-8000-000000000001',
    email: `${role.toLowerCase()}@example.test`,
    role,
    mfaEnabled: role !== 'PATIENT',
  },
});

const SESSIONS: Record<string, object | null> = {
  none: null,
  MFA_PENDING: { state: 'MFA_PENDING' },
  MFA_ENROLLMENT_REQUIRED: { state: 'MFA_ENROLLMENT_REQUIRED' },
  PATIENT: active('PATIENT'),
  STAFF: active('STAFF'),
  DOCTOR: active('DOCTOR'),
  ADMIN: active('ADMIN'),
  ADMIN_SETUP: { ...active('ADMIN'), setupRequired: true },
};

function sendJson(res: ServerResponse, status: number, body: object) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(body));
}

const apiError = (code: string, message: string) => ({
  error: { code, message, requestId: '00000000-0000-4000-8000-000000000000' },
});

export function mockApi(): Plugin {
  let current = 'none';

  return {
    name: 'doctorholiday-mock-api',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/__mock/session', (req, res) => {
        const value = new URL(req.url ?? '/', 'http://mock').searchParams.get('as') ?? '';
        if (!(value in SESSIONS)) {
          res.statusCode = 400;
          res.end(`Unknown session. Use ?as=${Object.keys(SESSIONS).join('|')}`);
          return;
        }
        current = value;
        res.statusCode = 302;
        res.setHeader('Location', '/');
        res.end();
      });

      server.middlewares.use('/api', (req, res) => {
        const { pathname } = new URL(req.url ?? '/', 'http://mock');
        if (req.method === 'GET' && pathname === '/v1/auth/me') {
          const session = SESSIONS[current];
          if (session) sendJson(res, 200, session);
          else sendJson(res, 401, apiError('UNAUTHENTICATED', 'Login required.'));
          return;
        }
        sendJson(res, 503, apiError('SERVICE_UNAVAILABLE', 'Not mocked.'));
      });

      server.httpServer?.once('listening', () => {
        server.config.logger.info(
          `  ➜  Mock API: no backend; switch session via /__mock/session?as=${Object.keys(SESSIONS).join('|')}`,
        );
      });
    },
  };
}
