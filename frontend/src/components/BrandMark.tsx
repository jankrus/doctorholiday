import { Flex, Text } from '@radix-ui/themes';
import './BrandMark.css';

/** Logo: a rounded medical cross on the accent colour, followed by the product name. */
export function BrandMark({ size = 'medium' }: { size?: 'medium' | 'large' }) {
  const large = size === 'large';
  return (
    <Flex align="center" gap="3">
      <svg
        className="brand-mark__logo"
        width={large ? 40 : 32}
        height={large ? 40 : 32}
        viewBox="0 0 32 32"
        aria-hidden="true"
        focusable="false"
      >
        <rect className="brand-mark__tile" width="32" height="32" rx="9" />
        <path
          className="brand-mark__cross"
          d="M13.5 8.5a1.5 1.5 0 0 1 1.5-1.5h2a1.5 1.5 0 0 1 1.5 1.5v5h5a1.5 1.5 0 0 1 1.5 1.5v2a1.5 1.5 0 0 1-1.5 1.5h-5v5a1.5 1.5 0 0 1-1.5 1.5h-2a1.5 1.5 0 0 1-1.5-1.5v-5h-5A1.5 1.5 0 0 1 7 17v-2a1.5 1.5 0 0 1 1.5-1.5h5v-5Z"
        />
      </svg>
      <Text size={large ? '5' : '4'} weight="bold" className="brand-mark__name">
        Doctor Holiday
      </Text>
    </Flex>
  );
}
