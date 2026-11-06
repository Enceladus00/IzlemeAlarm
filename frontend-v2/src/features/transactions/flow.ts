/** Exact money arithmetic in minor units (cents) for the transaction views. */

/** Parses a decimal string ("9500.00", "125.5", "-3") into integer cents. */
export function toCents(amount: string | number): bigint {
  const text = String(amount).trim();
  const match = /^(-?)(\d+)(?:\.(\d{1,}))?$/.exec(text);
  if (!match) return BigInt(Math.round(Number(text) * 100));
  const [, sign, whole, fraction = ''] = match;
  const cents = BigInt(whole!) * 100n + BigInt((fraction + '00').slice(0, 2));
  return sign ? -cents : cents;
}

/** Cents back to a plain decimal string with two places ("19300.00"). */
export function centsToDecimal(cents: bigint): string {
  const negative = cents < 0n;
  const absolute = negative ? -cents : cents;
  const whole = absolute / 100n;
  const fraction = String(absolute % 100n).padStart(2, '0');
  return `${negative ? '-' : ''}${whole}.${fraction}`;
}
