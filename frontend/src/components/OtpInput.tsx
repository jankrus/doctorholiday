import { useRef, useState, type ClipboardEvent, type KeyboardEvent } from 'react';
import type { FieldControlProps } from './FormField';
import './OtpInput.css';

type OtpInputProps = FieldControlProps & {
  /** Group label for screen readers; the visible label points at the first digit. */
  label: string;
  /** Name of the hidden input that carries the joined code in the form data. */
  name: string;
  length?: number;
  autoFocus?: boolean;
};

/**
 * One box per digit with automatic focus switching. Typing moves on, Backspace on an empty box
 * moves back, arrows navigate, and a pasted or autofilled code ("123 456") is spread over the
 * boxes. Only digits are accepted. To clear it, remount it with a new `key`.
 */
export function OtpInput({
  id,
  label,
  name,
  length = 6,
  autoFocus,
  'aria-invalid': invalid,
  'aria-describedby': describedBy,
}: OtpInputProps) {
  const [digits, setDigits] = useState<string[]>(() => Array(length).fill(''));
  const boxes = useRef<(HTMLInputElement | null)[]>([]);

  const focus = (index: number) => boxes.current[Math.max(0, Math.min(index, length - 1))]?.focus();

  /** Writes `value` (digits only) into the boxes from `start` on and focuses the next empty one. */
  function fill(start: number, value: string) {
    const incoming = value
      .replace(/\D/g, '')
      .slice(0, length - start)
      .split('');
    if (incoming.length === 0) return;
    setDigits((current) => {
      const next = [...current];
      incoming.forEach((digit, offset) => (next[start + offset] = digit));
      return next;
    });
    focus(start + incoming.length);
  }

  function handleChange(index: number, raw: string) {
    if (raw === '') {
      setDigits((current) => current.map((digit, i) => (i === index ? '' : digit)));
      return;
    }
    // Typing into a filled box whose content is not selected yields two characters: keep the new one.
    const previous = digits[index];
    const value = raw.length === 2 && previous ? raw.replace(previous, '') || previous : raw;
    fill(index, value);
  }

  function handleKeyDown(index: number, event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Backspace' && !digits[index] && index > 0) {
      event.preventDefault();
      setDigits((current) => current.map((digit, i) => (i === index - 1 ? '' : digit)));
      focus(index - 1);
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      focus(index - 1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      focus(index + 1);
    }
  }

  function handlePaste(index: number, event: ClipboardEvent<HTMLInputElement>) {
    event.preventDefault();
    fill(index, event.clipboardData.getData('text'));
  }

  return (
    <div role="group" aria-label={label} aria-describedby={describedBy} className="otp-input">
      {digits.map((digit, index) => (
        <input
          key={index}
          ref={(element) => {
            boxes.current[index] = element;
          }}
          id={index === 0 ? id : undefined}
          className="otp-input__digit"
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete={index === 0 ? 'one-time-code' : 'off'}
          aria-label={`Ziffer ${index + 1} von ${length}`}
          aria-invalid={invalid}
          aria-describedby={index === 0 ? describedBy : undefined}
          autoFocus={autoFocus && index === 0}
          value={digit}
          onChange={(event) => handleChange(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          onPaste={(event) => handlePaste(index, event)}
          onFocus={(event) => event.target.select()}
        />
      ))}
      <input type="hidden" name={name} value={digits.join('')} />
    </div>
  );
}
