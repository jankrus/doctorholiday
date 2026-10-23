import { Flex, Text } from '@radix-ui/themes';
import { useId, type ReactNode } from 'react';
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
