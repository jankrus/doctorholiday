import { Text } from '@radix-ui/themes';
import type { ReactNode } from 'react';
import { CheckIcon, DotIcon } from './icons';
import './Requirement.css';

/** One line of a live checklist (e.g. password rules): turns green with a tick once met. */
export function Requirement({ met, children }: { met: boolean; children: ReactNode }) {
  return (
    <Text
      as="p"
      size="2"
      color={met ? undefined : 'gray'}
      className="requirement"
      data-met={met || undefined}
    >
      {met ? <CheckIcon size={16} /> : <DotIcon size={16} />}
      <span className="sr-only">{met ? 'Erfüllt: ' : 'Noch nicht erfüllt: '}</span>
      {children}
    </Text>
  );
}
