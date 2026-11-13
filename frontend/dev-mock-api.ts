import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Plugin } from 'vite';
import { addDays, dateKey, startOfDay } from './src/appointments/time.ts';

// Dev server only (`apply: 'serve'`, never part of the build): answers /api while no backend runs,
// so the pages can be viewed and the auth flows clicked through. The frontend code is unchanged
// and talks to it like to the backend. All values are dummies; nothing is checked for real.
// Pick a session directly with http://localhost:5173/__mock/session?as=<one of SESSIONS>.

type Role = 'PATIENT' | 'STAFF' | 'DOCTOR' | 'ADMIN';
type Session = Record<string, unknown>;

const active = (role: string, email = `${role.toLowerCase()}@example.test`) => ({
  state: 'ACTIVE',
  user: {
    id: '00000000-0000-4000-8000-000000000001',
    email,
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

// Appointments (#25): two doctors with working hours Monday to Friday, 08:00-12:00 and 14:00-17:00
// practice time, like the backend's seed data. Times at minute 45 are "taken by someone else" when
// booked, so the 409 handling can be tried out.
const DOCTOR_A = { id: '00000000-0000-4000-8000-0000000000d1', displayName: 'Dr. Anna Berger' };
const DOCTOR_B = { id: '00000000-0000-4000-8000-0000000000d2', displayName: 'Dr. Mehmet Yilmaz' };
const DOCTORS = [DOCTOR_A, DOCTOR_B];
const WORKING_HOURS: [number, number][] = [
  [8, 12],
  [14, 17],
];
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

type MockAppointment = {
  id: string;
  status: 'BOOKED' | 'CANCELLED';
  reason: string;
  doctor: { id: string; displayName: string };
  startsAt: string;
  endsAt: string;
  bookedBy: 'PATIENT' | 'PRACTICE';
  createdAt: string;
  cancelledAt?: string;
  cancelledBy?: 'PATIENT' | 'PRACTICE';
};

/** Every start time of `doctorId` in [from, to), ignoring bookings. */
function workingStarts(doctorId: string, from: Date, to: Date, minutes: number): Date[] {
  const starts: Date[] = [];
  for (let day = dateKey(from); startOfDay(day) < to; day = addDays(day, 1)) {
    const weekday = new Date(`${day}T12:00:00Z`).getUTCDay();
    // Doctor 2 does not work on Wednesdays, so the filter makes a visible difference.
    if (weekday === 0 || weekday === 6 || (doctorId === DOCTOR_B.id && weekday === 3)) continue;
    const midnight = startOfDay(day).getTime();
    for (const [startHour, endHour] of WORKING_HOURS) {
      // Local hours from midnight; days with a DST change are close enough for a mock.
      for (
        let t = startHour * HOUR;
        t + minutes * MINUTE <= endHour * HOUR;
        t += minutes * MINUTE
      ) {
        const start = new Date(midnight + t);
        if (start >= from && start < to) starts.push(start);
      }
    }
  }
  return starts;
}

function seedAppointments(minutes: number): MockAppointment[] {
  const now = Date.now();
  const at = (days: number, hour: number) =>
    new Date(startOfDay(addDays(dateKey(new Date(now)), days)).getTime() + hour * HOUR);
  const make = (
    id: number,
    start: Date,
    doctor: number,
    reason: string,
    extra: Partial<MockAppointment> = {},
  ): MockAppointment => ({
    id: `00000000-0000-4000-8000-0000000000a${id}`,
    status: 'BOOKED',
    reason,
    doctor: doctor === 1 ? DOCTOR_B : DOCTOR_A,
    startsAt: start.toISOString(),
    endsAt: new Date(start.getTime() + minutes * MINUTE).toISOString(),
    bookedBy: 'PATIENT',
    createdAt: new Date(now - 7 * DAY).toISOString(),
    ...extra,
  });
  return [
    make(1, at(1, 9), 0, 'CHECKUP'), // within the 24-hour deadline: locked
    make(2, at(6, 10.5), 1, 'BLOOD_TEST_FASTING'),
    make(3, at(13, 15), 0, 'FOLLOW_UP', { bookedBy: 'PRACTICE' }),
    make(4, at(-12, 8.25), 1, 'VACCINATION'),
    make(5, at(9, 11), 0, 'CONSULTATION', {
      status: 'CANCELLED',
      cancelledAt: new Date(now - DAY).toISOString(),
      cancelledBy: 'PRACTICE',
    }),
  ];
}

export function mockApi(): Plugin {
  let session: Session | null = null;
  // Role the session gets once the MFA step is done.
  let pendingRole: Role = 'PATIENT';
  let setupDone = false;
  // Per patient e-mail, like `user.mfa_offer_declined_at` per account: optional MFA offer
  // (BR-26) still open (default for every new address), declined, or MFA enabled.
  const patientMfa = new Map<string, 'offer' | 'declined' | 'enabled'>();
  let currentEmail = '';
  let secretPending = false;
  let settings = {
    practiceName: 'Doctor Holiday',
    cancellationDeadlineHours: 24,
    appointmentMinutes: 15,
    updatedAt: new Date().toISOString(),
  };

  let appointments = seedAppointments(settings.appointmentMinutes);
  // Times someone else "booked" after a simulated conflict.
  const takenByOthers = new Set<string>();

  const isFree = (doctorId: string, start: Date, ignoreId?: string) => {
    const end = start.getTime() + settings.appointmentMinutes * MINUTE;
    return (
      !takenByOthers.has(`${doctorId}|${start.toISOString()}`) &&
      !appointments.some(
        (a) =>
          a.id !== ignoreId &&
          a.status === 'BOOKED' &&
          a.doctor.id === doctorId &&
          new Date(a.startsAt).getTime() < end &&
          new Date(a.endsAt).getTime() > start.getTime(),
      )
    );
  };

  const isOffered = (doctorId: string, start: Date, ignoreId?: string) =>
    start.getTime() > Date.now() &&
    start.getTime() <= Date.now() + 365 * DAY &&
    workingStarts(doctorId, start, new Date(start.getTime() + 1), settings.appointmentMinutes)
      .length === 1 &&
    isFree(doctorId, start, ignoreId);

  const page = <T>(items: T[], query: URLSearchParams) => {
    const limit = Number(query.get('limit') ?? 20);
    const offset = Number(query.get('offset') ?? 0);
    return { items: items.slice(offset, offset + limit), limit, offset, total: items.length };
  };

  const patientSession = () => (session?.user as { role?: Role } | undefined)?.role === 'PATIENT';

  const deadlinePassed = (a: MockAppointment) =>
    Date.now() > new Date(a.startsAt).getTime() - settings.cancellationDeadlineHours * HOUR;

  const activeSession = (role: Role): Session => {
    const session = active(role, currentEmail || undefined);
    if (role === 'PATIENT') {
      const mfa = patientMfa.get(currentEmail) ?? 'offer';
      session.user.mfaEnabled = mfa === 'enabled';
      if (mfa === 'offer') Object.assign(session.user, { mfaOfferPending: true });
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
        appointments = seedAppointments(settings.appointmentMinutes);
        takenByOthers.clear();
        if (value === 'ADMIN' || value === 'ADMIN_SETUP') setupDone = value === 'ADMIN';
        currentEmail = value.startsWith('PATIENT') ? 'patient@example.test' : '';
        if (value === 'PATIENT_MFA_OFFER') patientMfa.set(currentEmail, 'offer');
        if (value === 'PATIENT') patientMfa.set(currentEmail, 'declined');
        pendingRole = value === 'MFA_PENDING' ? 'DOCTOR' : 'ADMIN';
        res.statusCode = 302;
        res.setHeader('Location', '/');
        res.end();
      });

      server.middlewares.use('/api', async (req, res) => {
        const { pathname, searchParams: query } = new URL(req.url ?? '/', 'http://mock');
        const action = /^\/v1\/appointments\/([0-9a-f-]{36})\/(cancel|reschedule)$/.exec(pathname);
        const route = action
          ? `${req.method} /v1/appointments/{id}/${action[2]}`
          : `${req.method} ${pathname}`;

        switch (route) {
          case 'GET /v1/doctors':
            sendJson(res, 200, page(DOCTORS, query));
            return;

          case 'GET /v1/availability': {
            const from = new Date(query.get('from') ?? '');
            const to = new Date(query.get('to') ?? '');
            if (
              Number.isNaN(from.getTime()) ||
              Number.isNaN(to.getTime()) ||
              to <= from ||
              to.getTime() - from.getTime() > 31 * DAY
            ) {
              sendJson(res, 422, apiError('VALIDATION_ERROR', 'Invalid range.'));
              return;
            }
            const doctorId = query.get('doctorId');
            const minutes = settings.appointmentMinutes;
            const times = DOCTORS.filter((d) => !doctorId || d.id === doctorId)
              .flatMap((doctor) =>
                workingStarts(doctor.id, from, to, minutes)
                  .filter((start) => isOffered(doctor.id, start))
                  .map((start) => ({
                    doctor,
                    startsAt: start.toISOString(),
                    endsAt: new Date(start.getTime() + minutes * MINUTE).toISOString(),
                  })),
              )
              .sort(
                (a, b) =>
                  a.startsAt.localeCompare(b.startsAt) ||
                  a.doctor.displayName.localeCompare(b.doctor.displayName),
              );
            sendJson(res, 200, page(times, query));
            return;
          }

          case 'GET /v1/appointments/me': {
            const status = query.get('status');
            const from = query.get('from');
            const to = query.get('to');
            const items = appointments
              .filter(
                (a) =>
                  (!status || a.status === status) &&
                  (!from || a.startsAt >= new Date(from).toISOString()) &&
                  (!to || a.startsAt < new Date(to).toISOString()),
              )
              .sort((a, b) => a.startsAt.localeCompare(b.startsAt));
            sendJson(res, 200, page(items, query));
            return;
          }

          case 'POST /v1/appointments': {
            const body = (await readJson(req)) as Record<string, string>;
            const doctor = DOCTORS.find((d) => d.id === body.doctorId);
            const start = new Date(body.startsAt ?? '');
            if (!patientSession()) {
              sendJson(res, 403, apiError('FORBIDDEN', 'Not allowed.'));
            } else if (!doctor) {
              sendJson(res, 404, apiError('NOT_FOUND', 'Not found.'));
            } else if (
              appointments.filter(
                (a) => a.status === 'BOOKED' && new Date(a.endsAt).getTime() > Date.now(),
              ).length >= 5
            ) {
              sendJson(res, 409, apiError('APPOINTMENT_LIMIT_REACHED', 'Limit reached.'));
            } else if (!isOffered(doctor.id, start)) {
              sendJson(res, 409, apiError('TIME_NOT_AVAILABLE', 'Not available.'));
            } else if (new Date(start).getUTCMinutes() === 45) {
              takenByOthers.add(`${doctor.id}|${start.toISOString()}`);
              sendJson(res, 409, apiError('TIME_ALREADY_BOOKED', 'Already booked.'));
            } else {
              const appointment: MockAppointment = {
                id: crypto.randomUUID(),
                status: 'BOOKED',
                reason: body.reason ?? 'OTHER',
                doctor,
                startsAt: start.toISOString(),
                endsAt: new Date(
                  start.getTime() + settings.appointmentMinutes * MINUTE,
                ).toISOString(),
                bookedBy: 'PATIENT',
                createdAt: new Date().toISOString(),
              };
              appointments.push(appointment);
              sendJson(res, 201, appointment);
            }
            return;
          }

          case 'POST /v1/appointments/{id}/cancel':
          case 'POST /v1/appointments/{id}/reschedule': {
            const appointment = appointments.find((a) => a.id === action?.[1]);
            if (!patientSession() || !appointment) {
              sendJson(res, 404, apiError('NOT_FOUND', 'Not found.'));
              return;
            }
            const started = new Date(appointment.startsAt).getTime() <= Date.now();
            if (appointment.status !== 'BOOKED' || started) {
              const code =
                action?.[2] === 'cancel'
                  ? 'APPOINTMENT_NOT_CANCELLABLE'
                  : 'APPOINTMENT_NOT_RESCHEDULABLE';
              sendJson(res, 409, apiError(code, 'Not possible.'));
              return;
            }
            if (deadlinePassed(appointment)) {
              sendJson(res, 409, apiError('CANCELLATION_DEADLINE_PASSED', 'Too late.'));
              return;
            }
            if (action?.[2] === 'cancel') {
              Object.assign(appointment, {
                status: 'CANCELLED',
                cancelledAt: new Date().toISOString(),
                cancelledBy: 'PATIENT',
              });
              sendJson(res, 200, appointment);
              return;
            }
            const body = (await readJson(req)) as Record<string, string>;
            const doctor = DOCTORS.find((d) => d.id === (body.doctorId ?? appointment.doctor.id));
            const start = new Date(body.startsAt ?? '');
            if (!doctor) {
              sendJson(res, 404, apiError('NOT_FOUND', 'Not found.'));
            } else if (!isOffered(doctor.id, start, appointment.id)) {
              sendJson(res, 409, apiError('TIME_NOT_AVAILABLE', 'Not available.'));
            } else {
              Object.assign(appointment, {
                doctor,
                startsAt: start.toISOString(),
                endsAt: new Date(
                  start.getTime() + settings.appointmentMinutes * MINUTE,
                ).toISOString(),
              });
              sendJson(res, 200, appointment);
            }
            return;
          }

          case 'GET /v1/auth/me':
            if (session) sendJson(res, 200, session);
            else sendJson(res, 401, apiError('UNAUTHENTICATED', 'Login required.'));
            return;

          // E-mail decides the flow: any other address is a patient (with the MFA offer until that
          // address answers it), mfa@… needs a code, staff@…, doctor@… and admin@… must enrol MFA first,
          // limit@… is rate limited. Password "falsch" fails.
          case 'POST /v1/auth/login': {
            const { email = '', password = '' } = (await readJson(req)) as Record<string, string>;
            const name = email.split('@')[0]?.toLowerCase();
            currentEmail = email.trim().toLowerCase();
            if (name === 'limit') {
              sendJson(res, 429, apiError('RATE_LIMITED', 'Too many attempts.'));
            } else if (password === 'falsch') {
              sendJson(res, 401, apiError('INVALID_CREDENTIALS', 'Invalid credentials.'));
            } else if (name === 'mfa') {
              pendingRole = 'PATIENT';
              patientMfa.set(currentEmail, 'enabled');
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
              otpauthUri: `otpauth://totp/Doctor%20Holiday:${encodeURIComponent(currentEmail || 'user@example.test')}?secret=${SECRET}&issuer=Doctor%20Holiday`,
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
            if (enrolling && role === 'PATIENT') patientMfa.set(currentEmail, 'enabled');
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
            patientMfa.set(currentEmail, 'declined');
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
            sendJson(res, 500, apiError('INTERNAL_ERROR', 'Not mocked.'));
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
