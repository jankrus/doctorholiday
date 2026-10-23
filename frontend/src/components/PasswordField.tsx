import { IconButton, TextField } from '@radix-ui/themes';
import { forwardRef, useState, type ComponentPropsWithoutRef } from 'react';
import { EyeIcon, EyeOffIcon } from './icons';

type PasswordFieldProps = Omit<ComponentPropsWithoutRef<typeof TextField.Root>, 'type'>;

/**
 * Password input with a show/hide toggle, so long passphrases can be checked before sending.
 * The value is never copied anywhere; showing it only switches the input type.
 */
export const PasswordField = forwardRef<HTMLInputElement, PasswordFieldProps>(
  function PasswordField(props, ref) {
    const [visible, setVisible] = useState(false);

    return (
      <TextField.Root {...props} ref={ref} type={visible ? 'text' : 'password'}>
        <TextField.Slot side="right">
          <IconButton
            type="button"
            variant="ghost"
            color="gray"
            size="2"
            aria-label="Show password"
            aria-pressed={visible}
            aria-controls={props.id}
            onClick={() => setVisible((v) => !v)}
          >
            {visible ? <EyeOffIcon size={18} /> : <EyeIcon size={18} />}
          </IconButton>
        </TextField.Slot>
      </TextField.Root>
    );
  },
);
