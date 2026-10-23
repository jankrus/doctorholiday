import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderRoute } from '../../test/render';
import { activeSession, apiError, stubSession } from '../../test/session';

const pending = { ...activeSession('ADMIN'), setupRequired: true };
const seeded = {
  practiceName: 'Doctor Holiday',
  cancellationDeadlineHours: 24,
  appointmentMinutes: 15,
  updatedAt: '2026-10-23T08:00:00Z',
};

function renderSetup(save: () => Response = () => Response.json(seeded)) {
  let sent: unknown;
  stubSession(pending, {
    'GET /api/v1/settings': () => Response.json(seeded),
    'PUT /api/v1/settings': async (request, setSession) => {
      sent = await request.json();
      const response = save();
      if (response.ok) setSession(activeSession('ADMIN'));
      return response;
    },
  });
  return { router: renderRoute('/setup'), sent: () => sent };
}

async function replace(label: string, value: string) {
  const user = userEvent.setup();
  const field = await screen.findByLabelText(label);
  await user.clear(field);
  if (value) await user.type(field, value);
  return user;
}

describe('practice setup', () => {
  it('prefills the seeded settings', async () => {
    renderSetup();
    expect(await screen.findByLabelText('Name der Praxis')).toHaveValue('Doctor Holiday');
    expect(screen.getByLabelText('Absagefrist')).toHaveValue(24);
    expect(screen.getByLabelText('Termindauer')).toHaveValue(15);
  });

  it('saves the settings and opens the admin area', async () => {
    const { router, sent } = renderSetup();
    await replace('Name der Praxis', 'Praxis Dr. Sommer');
    const user = await replace('Termindauer', '20');
    await user.click(screen.getByRole('button', { name: 'Speichern und fortfahren' }));

    expect(await screen.findByRole('heading', { name: 'Verwaltung' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/admin');
    expect(sent()).toEqual({
      practiceName: 'Praxis Dr. Sommer',
      cancellationDeadlineHours: 24,
      appointmentMinutes: 20,
    });
  });

  it('shows field errors and sends nothing', async () => {
    const { sent } = renderSetup();
    await replace('Name der Praxis', '');
    const user = await replace('Absagefrist', '200');
    await user.click(screen.getByRole('button', { name: 'Speichern und fortfahren' }));

    const name = await screen.findByLabelText('Name der Praxis');
    expect(name).toHaveAccessibleDescription('Bitte geben Sie den Namen der Praxis ein.');
    expect(name).toHaveFocus();
    expect(screen.getByLabelText('Absagefrist')).toHaveAccessibleDescription(
      'Bitte geben Sie eine ganze Zahl von 0 bis 168 ein.',
    );
    expect(sent()).toBeUndefined();
  });

  it('shows a generic error from the server', async () => {
    renderSetup(() => apiError('VALIDATION_ERROR', 422));
    await userEvent.click(await screen.findByRole('button', { name: 'Speichern und fortfahren' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Bitte überprüfen Sie Ihre Eingaben.',
    );
  });
});
