// Browser hardening (#27): the CSP of the nginx image and an entry document it does not break.
import { describe, expect, it } from 'vitest';
import indexHtml from '../index.html?raw';
import securityHeaders from '../security-headers.conf?raw';
import nginxConf from '../nginx.conf?raw';

function directives(): Map<string, string[]> {
  const header = /add_header Content-Security-Policy "([^"]+)" always;/.exec(securityHeaders);
  expect(header, 'Content-Security-Policy is set with always').not.toBeNull();
  const parsed = new Map<string, string[]>();
  for (const part of (header?.[1] ?? '').split(';')) {
    const [name, ...values] = part.trim().split(/\s+/);
    if (name) parsed.set(name, values);
  }
  return parsed;
}

describe('Content-Security-Policy', () => {
  it('only allows the own origin and nothing for plugins, framing or foreign forms', () => {
    const csp = directives();

    expect(csp.get('default-src')).toEqual(["'self'"]);
    expect(csp.get('script-src')).toEqual(["'self'"]);
    expect(csp.get('object-src')).toEqual(["'none'"]);
    expect(csp.get('frame-ancestors')).toEqual(["'none'"]);
    expect(csp.get('base-uri')).toEqual(["'self'"]);
    expect(csp.get('form-action')).toEqual(["'self'"]);
  });

  it('has no unsafe keyword and no host or scheme wildcard', () => {
    const values = [...directives().values()].flat();

    expect(values.filter((value) => value.startsWith("'unsafe-"))).toEqual([]);
    expect(values.filter((value) => value.includes('*') || /^https?:/.test(value))).toEqual([]);
  });

  it('is part of the shared header file that every location includes', () => {
    const includes = nginxConf.match(/include \/etc\/nginx\/security-headers\.conf;/g) ?? [];

    expect(includes).toHaveLength(2);
  });
});

describe('index.html under that policy', () => {
  it('has no inline script, inline style or event handler attribute', () => {
    const inlineScripts = [...indexHtml.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)].filter(
      ([, attributes, body]) => !/\bsrc=/.test(attributes ?? '') || (body ?? '').trim() !== '',
    );

    expect(inlineScripts).toEqual([]);
    expect(indexHtml).not.toMatch(/<style\b/i);
    expect(indexHtml).not.toMatch(/\sstyle=/i);
    expect(indexHtml).not.toMatch(/\son[a-z]+=/i);
  });
});
