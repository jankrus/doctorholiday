import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Plugin } from 'vite';

// Dev server only (`apply: 'serve'`, never part of the build): answers /api while no backend runs,
// so the pages can be viewed and the auth flows clicked through. The frontend code is unchanged
// and talks to it like to the backend. All values are dummies; nothing is checked for real.
// Pick a session directly with http://localhost:5173/__mock/session?as=<one of SESSIONS>.

type Role = 'PATIENT' | 'STAFF' | 'DOCTOR' | 'ADMIN';
type Session = Record<string, unknown>;

const active = (role: string) => ({
  state: 'ACTIVE',
  user: {
    id: '00000000-0000-4000-8000-000000000001',
    email: `${role.toLowerCase()}@example.test`,
    role,
    mfaEnabled: role !== 'PATIENT',
  },
});

const SESSIONS: Record<string, Session | null> = {
  none: null,
  MFA_PENDING: { state: 'MFA_PENDING' },
  MFA_ENROLLMENT_REQUIRED: { state: 'MFA_ENROLLMENT_REQUIRED' },
  PATIENT: active('PATIENT'),
  PATIENT_MFA_OFFER: {
    ...active('PATIENT'),
    user: { ...active('PATIENT').user, mfaOfferPending: true },
  },
  STAFF: active('STAFF'),
  DOCTOR: active('DOCTOR'),
  ADMIN: active('ADMIN'),
  ADMIN_SETUP: { ...active('ADMIN'), setupRequired: true },
};

// Well-known example secret from TOTP documentation; not a real credential.
const SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP';
const RECOVERY_CODES = [
  'k7m2p-q4x5z',
  'abcde-fghij',
  'mnopq-rstuv',
  'wxyz2-34567',
  'qwert-zuiop',
  'asdfg-hjklm',
  'yxcvb-nmqwe',
  'pomnb-vcxyl',
  'kjhgf-dsaqw',
  'zt5r4-e3w2q',
];

function sendJson(res: ServerResponse, status: number, body: object) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(body));
}

function sendEmpty(res: ServerResponse, status: number) {
  res.statusCode = status;
  res.end();
}

const apiError = (code: string, message: string) => ({
  error: { code, message, requestId: '00000000-0000-4000-8000-000000000000' },
});

async function readJson(req: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
  } catch {
    return {};
  }
}

export function mockApi(): Plugin {
  let session: Session | null = null;
  // Role the session gets once the MFA step is done.
  let pendingRole: Role = 'PATIENT';
  let setupDone = false;
  // Patients: optional MFA offer (BR-26) still open, declined, or MFA enabled.
  let patientMfa: 'offer' | 'declined' | 'enabled' = 'offer';
  let secretPending = false;
  let settings = {
    practiceName: 'Doctor Holiday',
    cancellationDeadlineHours: 24,
    appointmentMinutes: 15,
    updatedAt: new Date().toISOString(),
  };

  const activeSession = (role: Role): Session => {
    const session = active(role);
    if (role === 'PATIENT') {
      session.user.mfaEnabled = patientMfa === 'enabled';
      if (patientMfa === 'offer') Object.assign(session.user, { mfaOfferPending: true });
    }
    return { ...session, ...(role === 'ADMIN' && !setupDone ? { setupRequired: true } : {}) };
  };

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
        session = SESSIONS[value] ?? null;
        if (value === 'ADMIN' || value === 'ADMIN_SETUP') setupDone = value === 'ADMIN';
        if (value === 'PATIENT_MFA_OFFER') patientMfa = 'offer';
        if (value === 'PATIENT') patientMfa = 'declined';
        pendingRole = value === 'MFA_PENDING' ? 'DOCTOR' : 'ADMIN';
        res.statusCode = 302;
        res.setHeader('Location', '/');
        res.end();
      });

      server.middlewares.use('/api', async (req, res) => {
        const { pathname } = new URL(req.url ?? '/', 'http://mock');
        const route = `${req.method} ${pathname}`;

        switch (route) {
          case 'GET /v1/auth/me':
            if (session) sendJson(res, 200, session);
            else sendJson(res, 401, apiError('UNAUTHENTICATED', 'Login required.'));
            return;

          // E-mail decides the flow: patient@… logs in directly (with the MFA offer until it is
          // answered), mfa@… needs a code, staff@…, doctor@… and admin@… must enrol MFA first,
          // limit@… is rate limited. Password "falsch" fails.
          case 'POST /v1/auth/login': {
            const { email = '', password = '' } = (await readJson(req)) as Record<string, string>;
            const name = email.split('@')[0]?.toLowerCase();
            if (name === 'limit') {
              sendJson(res, 429, apiError('RATE_LIMITED', 'Too many attempts.'));
            } else if (password === 'falsch') {
              sendJson(res, 401, apiError('INVALID_CREDENTIALS', 'Invalid credentials.'));
            } else if (name === 'mfa') {
              pendingRole = 'PATIENT';
              patientMfa = 'enabled';
              session = { state: 'MFA_PENDING' };
              sendJson(res, 200, session);
            } else if (name === 'staff' || name === 'doctor' || name === 'admin') {
              pendingRole = name.toUpperCase() as Role;
              session = { state: 'MFA_ENROLLMENT_REQUIRED' };
              sendJson(res, 200, session);
            } else {
              session = activeSession('PATIENT');
              sendJson(res, 200, session);
            }
            return;
          }

          case 'POST /v1/auth/register':
            sendEmpty(res, 202);
            return;

          case 'POST /v1/auth/logout':
            session = null;
            sendEmpty(res, 204);
            return;

          case 'POST /v1/auth/mfa/enroll':
            secretPending = true;
            sendJson(res, 200, {
              secret: SECRET,
              otpauthUri: `otpauth://totp/Doctor%20Holiday:${pendingRole.toLowerCase()}%40example.test?secret=${SECRET}&issuer=Doctor%20Holiday`,
            });
            return;

          // Every code is accepted except 000000.
          case 'POST /v1/auth/mfa/verify': {
            const body = await readJson(req);
            if (body.code === '000000' || !session) {
              sendJson(res, 400, apiError('INVALID_MFA_CODE', 'Invalid code.'));
              return;
            }
            const enrolling = secretPending;
            secretPending = false;
            const role = (session.user as { role?: Role } | undefined)?.role ?? pendingRole;
            if (enrolling && role === 'PATIENT') patientMfa = 'enabled';
            session = activeSession(role);
            sendJson(
              res,
              200,
              enrolling ? { session, recoveryCodes: RECOVERY_CODES } : { session },
            );
            return;
          }

          case 'POST /v1/auth/mfa/decline': {
            const user = session?.user as { role?: Role } | undefined;
            if (user?.role !== 'PATIENT') {
              sendJson(res, 403, apiError('FORBIDDEN', 'Not allowed.'));
              return;
            }
            patientMfa = 'declined';
            session = activeSession('PATIENT');
            sendEmpty(res, 204);
            return;
          }

          case 'GET /v1/settings':
            sendJson(res, 200, settings);
            return;

          case 'PUT /v1/settings': {
            const body = await readJson(req);
            settings = { ...settings, ...body, updatedAt: new Date().toISOString() };
            setupDone = true;
            if (session) delete session.setupRequired;
            sendJson(res, 200, settings);
            return;
          }

          default:
            sendJson(res, 503, apiError('SERVICE_UNAVAILABLE', 'Not mocked.'));
        }
      });

      server.httpServer?.once('listening', () => {
        server.config.logger.info(
          `  ➜  Mock API: no backend; switch session via /__mock/session?as=${Object.keys(SESSIONS).join('|')}`,
        );
      });
    },
  };
}
