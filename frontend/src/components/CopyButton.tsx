import { Button } from '@radix-ui/themes';
import { useEffect, useState, type ReactNode } from 'react';
import { CheckIcon, CopyIcon } from './icons';

/** Copies `text` to the clipboard and confirms it for two seconds. */
export function CopyButton({ text, children }: { text: string; children: ReactNode }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      // No clipboard access (e.g. denied permission): the text stays visible for manual copying.
    }
  }

  return (
    <Button type="button" variant="soft" size="2" onClick={copy}>
      {copied ? <CheckIcon /> : <CopyIcon />}
      <span aria-live="polite">{copied ? 'Kopiert' : children}</span>
    </Button>
  );
}
