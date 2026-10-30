import { useMemo } from 'react';
import { encode } from 'uqr';
import './QrCode.css';

/**
 * QR code drawn in the browser as SVG. The value (an `otpauth://` URI with the TOTP secret) never
 * leaves the page: no QR web service, no image request.
 */
export function QrCode({
  value,
  label,
  size = 192,
}: {
  value: string;
  label: string;
  size?: number;
}) {
  const { path, modules } = useMemo(() => {
    // Medium error correction and the 4-module quiet zone the QR standard asks for.
    const { data } = encode(value, { ecc: 'M', border: 4 });
    let d = '';
    data.forEach((row, y) =>
      row.forEach((dark, x) => {
        if (dark) d += `M${x} ${y}h1v1h-1z`;
      }),
    );
    return { path: d, modules: data.length };
  }, [value]);

  return (
    <svg
      role="img"
      aria-label={label}
      width={size}
      height={size}
      viewBox={`0 0 ${modules} ${modules}`}
      shapeRendering="crispEdges"
      className="qr-code"
    >
      <rect width={modules} height={modules} className="qr-code__background" />
      <path d={path} className="qr-code__modules" />
    </svg>
  );
}
