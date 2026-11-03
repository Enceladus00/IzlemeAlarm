import type { Rule, RuleParameter } from '@/api/schemas/rules';

/** Parameter lists copied from the real GET /rules response. */
const p = (name: string, type: string, unit: string, required = true): RuleParameter => ({
  name,
  type,
  unit,
  meaning: `Meaning of ${name}.`,
  required,
});

const meta = (parameters: RuleParameter[], feasibility = 'MEDIUM') => ({
  steps: ['Collect transactions.', 'Score against anchors.'],
  alert_mode: 'ALERT',
  parameters,
  analyst_review_notes: ['Confirm thresholds with compliance.'],
  feasibility,
  feasibility_reason: 'Requires approved thresholds.',
});

const unset = { BIREYSEL: { status: 'UNSET', values: {} }, KURUMSAL: { status: 'UNSET', values: {} } };

export const ruleFixtures: Rule[] = [
  {
    rule_code: 'R02',
    name: 'Large single transaction',
    description: 'One outgoing transfer above the configured limit.',
    is_active: false,
    weight: '0.450',
    thresholds: { BIREYSEL: { status: 'APPROVED', values: { limits: { TRY: '50000.0' } } }, KURUMSAL: { status: 'UNSET', values: {} } },
    metadata: meta([p('limits', 'map[currency, decimal]', 'currency')], 'HIGH'),
  },
  {
    rule_code: 'R01',
    name: 'Near-limit activity',
    description: 'Repeated transfers just below the limit.',
    is_active: false,
    weight: '1.000',
    thresholds: unset,
    metadata: meta([
      p('limits', 'map[currency, decimal]', 'currency'),
      p('x_esik', 'integer', 'transaction count'),
      p('x_kesin', 'integer', 'transaction count'),
      p('minimum_income_ratio', 'decimal', 'ratio'),
      p('income_currency', 'ISO currency', 'currency'),
      p('window_days', 'integer', 'days'),
      p('band_low', 'decimal', 'ratio'),
      p('above_check', 'decimal', 'multiple'),
    ]),
  },
  {
    rule_code: 'R03',
    name: 'Repeated cash deposits',
    description: null,
    is_active: false,
    weight: '1.000',
    thresholds: unset,
    metadata: meta([
      p('limits', 'map[currency, decimal]', 'currency'),
      p('x_esik', 'integer', 'transaction count'),
      p('x_kesin', 'integer', 'transaction count'),
      p('cash_channels', 'list[channel]', 'channel'),
      p('window_days', 'integer', 'days'),
    ]),
  },
  {
    rule_code: 'R06',
    name: 'Velocity increase',
    description: null,
    is_active: false,
    weight: '1.000',
    thresholds: unset,
    metadata: meta([
      p('history_weeks', 'integer', 'weeks'),
      p('min_count', 'integer', 'transactions'),
      p('season_factor', 'date-to-decimal map', 'date:factor', false),
      p('x_esik', 'decimal', '-log10 probability'),
      p('x_kesin', 'decimal', '-log10 probability'),
    ]),
  },
  {
    rule_code: 'R13',
    name: 'Layering chains',
    description: null,
    is_active: true,
    weight: '1.000',
    thresholds: {
      BIREYSEL: {
        status: 'PROVISIONAL',
        values: { window_days: 7, max_step_hours: 24, decay_low: '0.5', decay_high: '0.9', max_depth: 5, cash_accounts: [3, 9], x_esik: 2, x_kesin: 4 },
      },
      KURUMSAL: { status: 'UNSET', values: {} },
    },
    metadata: meta(
      [
        p('window_days', 'integer', 'days'),
        p('max_step_hours', 'integer', 'hours'),
        p('decay_low', 'decimal', 'ratio'),
        p('decay_high', 'decimal', 'ratio'),
        p('max_depth', 'integer', 'transactions'),
        p('cash_accounts', 'account ID list', 'account_id', false),
        p('x_esik', 'integer', 'chain length'),
        p('x_kesin', 'integer', 'chain length'),
      ],
      'LOW',
    ),
  },
  {
    rule_code: 'R1',
    name: 'Threshold-adjacent repeated transactions',
    description: 'Legacy rule.',
    is_active: false,
    weight: '1.000',
    thresholds: { amount_limit: 10000, window_minutes: 60 },
    metadata: null,
  },
];

export function ruleByCode(code: string): Rule {
  return ruleFixtures.find((rule) => rule.rule_code === code)!;
}
