import type { Explanation } from '@/api/schemas/alerts';
import { formatNumber } from '@/utils/format';

/** Detail keys that hold a 0–1 share; templates use `<key>_pct`. */
const SHARE_KEYS = ['current_cash_share', 'baseline_cash_share', 'new_recipient_share'];

function isNumeric(value: unknown): value is string | number {
  return (typeof value === 'number' && Number.isFinite(value)) || (typeof value === 'string' && /^-?\d+(\.\d+)?$/.test(value));
}

/**
 * Values available to the rule's summary sentence: rule parameters, then every
 * step's details (later steps win), plus x (raw value) and score.
 */
export function explanationVariables(explanation: Explanation, language: string): Record<string, string> {
  const raw: Record<string, unknown> = { ...explanation.parameters };
  for (const step of explanation.steps) Object.assign(raw, step.details);
  raw.x = explanation.raw_x;
  raw.score = explanation.score;
  const vars: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw)) {
    if (value === null || value === undefined) continue;
    if (isNumeric(value)) {
      vars[key] = formatNumber(String(value), language, { maximumFractionDigits: 2 });
      if (SHARE_KEYS.includes(key)) {
        vars[`${key}_pct`] = formatNumber(String(Number(value) * 100), language, { maximumFractionDigits: 1 });
      }
    } else if (typeof value === 'string') {
      vars[key] = value;
    } else if (Array.isArray(value) && value.every((item) => typeof item === 'string')) {
      vars[key] = value.join(', ');
    }
  }
  return vars;
}

/**
 * Fills `{name}` placeholders; returns null when any value is missing. (Single
 * braces on purpose: the templates are read from the locale bundle directly, so
 * i18next never interpolates them.)
 */
export function fillTemplate(template: string, vars: Record<string, string>): string | null {
  let missing = false;
  const text = template.replace(/\{(\w+)\}/g, (_match, name: string) => {
    const value = vars[name];
    if (value === undefined) missing = true;
    return value ?? '';
  });
  return missing ? null : text;
}
