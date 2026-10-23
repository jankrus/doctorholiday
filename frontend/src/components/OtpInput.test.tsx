import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { OtpInput } from './OtpInput';

function renderOtp() {
  const { container } = render(
    <form>
      <OtpInput id="code" label="Bestätigungscode" name="code" />
    </form>,
  );
  const hidden = () => container.querySelector<HTMLInputElement>('input[type=hidden]')?.value;
  return { box: (n: number) => screen.getByLabelText(`Ziffer ${n} von 6`), hidden };
}

describe('OtpInput', () => {
  it('moves the focus on with every digit and joins the code for the form', async () => {
    const { box, hidden } = renderOtp();
    await userEvent.click(box(1));
    await userEvent.keyboard('123');
    expect(box(4)).toHaveFocus();
    await userEvent.keyboard('456');

    expect(hidden()).toBe('123456');
    expect(box(6)).toHaveFocus();
  });

  it('ignores everything but digits', async () => {
    const { box, hidden } = renderOtp();
    await userEvent.click(box(1));
    await userEvent.keyboard('1a 2');

    expect(hidden()).toBe('12');
    expect(box(3)).toHaveFocus();
  });

  it('goes back with Backspace on an empty box', async () => {
    const { box, hidden } = renderOtp();
    await userEvent.click(box(1));
    await userEvent.keyboard('12{Backspace}');

    expect(hidden()).toBe('1');
    expect(box(2)).toHaveFocus();
  });

  it('spreads a pasted code over the boxes', async () => {
    const { box, hidden } = renderOtp();
    await userEvent.click(box(1));
    await userEvent.paste('654 321');

    expect(hidden()).toBe('654321');
    expect(box(6)).toHaveFocus();
  });

  it('navigates with the arrow keys and overwrites a digit', async () => {
    const { box, hidden } = renderOtp();
    await userEvent.click(box(1));
    await userEvent.keyboard('123{ArrowLeft}{ArrowLeft}9');

    expect(hidden()).toBe('193');
  });

  it('is one labelled group for screen readers', () => {
    renderOtp();
    expect(screen.getByRole('group', { name: 'Bestätigungscode' })).toBeInTheDocument();
  });
});
