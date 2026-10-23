import { Flex, Text } from '@radix-ui/themes';
import { useEffect, useId, type ReactNode, type RefObject } from 'react';
import { AlertIcon } from './icons';
import './FormField.css';

/** Attributes that tie an input to its label, hint and error; spread them onto the input. */
export type FieldControlProps = {
  id: string;
  'aria-invalid'?: true;
  'aria-describedby'?: string;
};

type FormFieldProps = {
  label: string;
  optional?: boolean;
  /** Shown below the input while there is no error. */
  hint?: ReactNode;
  error?: string;
  children: (control: FieldControlProps) => ReactNode;
};

/** Label, input, hint and error message in the order screen readers announce them. */
export function FormField({ label, optional, hint, error, children }: FormFieldProps) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error ?? hint;

  return (
    <Flex direction="column" gap="2">
      <Text as="label" htmlFor={id} size="2" weight="medium">
        {label}
        {optional && (
          <Text color="gray" weight="regular">
            {' '}
            (optional)
          </Text>
        )}
      </Text>
      {children({
        id,
        'aria-invalid': error ? true : undefined,
        'aria-describedby': message ? messageId : undefined,
      })}
      {error ? (
        <Text id={messageId} size="2" color="red" className="form-field__error">
          <AlertIcon size={16} />
          {error}
        </Text>
      ) : (
        hint && (
          <Text as="div" id={messageId} size="2" color="gray">
            {hint}
          </Text>
        )
      )}
    </Flex>
  );
}

/**
 * After a failed submit, moves focus to the first field with an error (keys in form order), so
 * keyboard and screen reader users land on it.
 */
export function useFocusFirstError(
  form: RefObject<HTMLFormElement | null>,
  errors: Record<string, string | undefined> | undefined,
) {
  useEffect(() => {
    const first = Object.keys(errors ?? {})[0];
    const field = first && form.current?.elements.namedItem(first);
    if (field instanceof HTMLElement) field.focus();
  }, [form, errors]);
}
