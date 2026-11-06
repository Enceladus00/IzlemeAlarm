/**
 * E09 — plain-language rule explanations. For each registered rule this turns
 * the saved parameters of one customer type into interpolation values for the
 * `ruleText.<code>.sentence | yes | no` strings, so the numbers in the sentence
 * are always the rule's current parameters (never invented). Defaults mirror
 * backend/detection/parameters.py.
 */
import { formatNumber } from '@/utils/format';

export type RuleValues = Record<string, unknown>;
export type ExplainVars = Record<string, string>;

export const EXPLAINED_RULES = [
  'R01', 'R02', 'R03', 'R04', 'R05', 'R06', 'R07', 'R08', 'R09',
  'R10', 'R11', 'R12', 'R13', 'R14', 'R15', 'R16', 'R17', 'R18', 'S1', 'S2',
] as const;
export type ExplainedRule = (typeof EXPLAINED_RULES)[number];

/** Backend defaults for optional parameters (backend/detection/parameters.py). */
export function parameterDefault(code: string, name: string): unknown {
  if (name === 'window_days') return ['S1', 'S2', 'R17'].includes(code) ? 30 : 7;
  const defaults: Record<string, unknown> = {
    band_low: 0.9,
    above_check: 1.1,
    p: 4,
    alert_threshold: 0.5,
    excluded_rules: ['R02', 'R17', 'R18'],
    open_statuses: ['new', 'in_review'],
  };
  return defaults[name];
}

export function isExplained(code: string): code is ExplainedRule {
  return (EXPLAINED_RULES as readonly string[]).includes(code);
}

interface Context {
  language: string;
  /** Label for a transaction channel code (atm, branch …). */
  channel: (code: string) => string;
  /** Label for an alert status code (new, in_review …). */
  status: (code: string) => string;
}

class Missing extends Error {}

function makeHelpers(values: RuleValues, { language }: Context) {
  const raw = (name: string, fallback?: number): number => {
    const value = values[name];
    if (value === undefined || value === null || value === '') {
      if (fallback === undefined) throw new Missing(name);
      return fallback;
    }
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) throw new Missing(name);
    return numeric;
  };
  const num = (value: number, digits = 2) => formatNumber(value, language, { maximumFractionDigits: digits });
  const pct = (ratio: number) => num(ratio * 100, 1);
  const limitEntries = (): Array<[string, number]> => {
    const limits = values.limits;
    if (!limits || typeof limits !== 'object') throw new Missing('limits');
    const entries = Object.entries(limits as Record<string, unknown>)
      .map(([currency, amount]) => [currency, Number(amount)] as [string, number])
      .filter(([, amount]) => Number.isFinite(amount) && amount > 0);
    if (entries.length === 0) throw new Missing('limits');
    // TRY first: examples use the local currency when it is configured.
    return entries.sort(([a], [b]) => (a === 'TRY' ? -1 : b === 'TRY' ? 1 : a.localeCompare(b)));
  };
  const money = (amount: number, currency: string) => `${num(amount)} ${currency}`;
  const limits = () => limitEntries().map(([currency, amount]) => money(amount, currency)).join(', ');
  const firstLimit = () => limitEntries()[0]!;
  const list = (name: string, fallback?: string[]): string[] => {
    const value = values[name];
    if (Array.isArray(value) && value.length > 0) return value.map(String);
    if (fallback) return fallback;
    throw new Missing(name);
  };
  /** x_esik / x_kesin on a log-ratio scale, shown as multiples of the reference amount. */
  const logMultiples = () => ({ me: num(Math.exp(raw('x_esik'))), mk: num(Math.exp(raw('x_kesin'))) });
  const anchors = (digits = 2) => ({ xe: num(raw('x_esik'), digits), xk: num(raw('x_kesin'), digits) });
  return { raw, num, pct, money, limits, firstLimit, list, logMultiples, anchors };
}

type Builder = (h: ReturnType<typeof makeHelpers>, context: Context) => ExplainVars;

const BUILDERS: Record<ExplainedRule, Builder> = {
  R01: ({ raw, num, money, firstLimit, pct }) => {
    const [currency, limit] = firstLimit();
    const low = limit * raw('band_low', 0.9);
    const above = limit * raw('above_check', 1.1);
    return {
      window: num(raw('window_days', 7)),
      currency,
      limit: money(limit, currency),
      low: money(low, currency),
      above: money(above, currency),
      xe: num(raw('x_esik'), 0),
      xk: num(raw('x_kesin'), 0),
      ratio: pct(raw('minimum_income_ratio')),
      count: num(Math.max(raw('x_kesin'), 1), 0),
      sample: money(Math.round((low + limit) / 2), currency),
      sampleAbove: money(Math.round((limit + above) / 2), currency),
    };
  },
  R02: ({ money, limits, firstLimit }) => {
    const [currency, limit] = firstLimit();
    return { limits: limits(), over: money(limit * 1.2, currency), under: money(limit * 0.9, currency) };
  },
  R03: ({ raw, num, money, firstLimit, list }, { channel }) => {
    const [currency, limit] = firstLimit();
    return {
      window: num(raw('window_days', 7)),
      channels: list('cash_channels').map(channel).join(', '),
      limit: money(limit, currency),
      xe: num(raw('x_esik'), 0),
      xk: num(raw('x_kesin'), 0),
      sample: money(limit * 0.9, currency),
      over: money(limit * 1.1, currency),
    };
  },
  R04: ({ raw, num, money, anchors }) => {
    const income = 20_000;
    return {
      window: num(raw('window_days', 7)),
      ...anchors(),
      income: money(income, 'TRY'),
      yesAmount: money(income * raw('x_kesin'), 'TRY'),
      noAmount: money(income * raw('x_esik') * 0.8, 'TRY'),
    };
  },
  R05: ({ raw, num, anchors }) => ({ history: num(raw('history_days')), bands: num(raw('income_bands')), ...anchors() }),
  R06: ({ raw, num }) => {
    const minimum = raw('min_count');
    const xe = raw('x_esik');
    const xk = raw('x_kesin');
    // −log10(p) anchors shown as the probability itself; very small ones as a power of ten.
    const probability = (exponent: number) =>
      exponent > 6 ? `10^-${num(exponent)}` : num(10 ** -exponent, Math.max(2, Math.ceil(exponent) + 1));
    return {
      weeks: num(raw('history_weeks')),
      min: num(minimum, 0),
      pe: probability(xe),
      pk: probability(xk),
      busy: num(Math.max(40, minimum * 2), 0),
      few: num(Math.max(minimum - 1, 0), 0),
    };
  },
  R07: ({ raw, num, money, limits, firstLimit, logMultiples }) => {
    const [currency, limit] = firstLimit();
    const dormant = raw('dormant_days');
    return {
      dormant: num(dormant, 0),
      window: num(raw('window_days')),
      limits: limits(),
      ...logMultiples(),
      dormantPlus: num(dormant + 30, 0),
      recent: num(Math.max(Math.floor(dormant / 2), 1), 0),
      yesAmount: money(limit * Math.exp(raw('x_kesin')), currency),
    };
  },
  R08: ({ raw, num, money, limits, firstLimit, logMultiples }) => {
    const [currency, limit] = firstLimit();
    const age = raw('account_age_days');
    return {
      age: num(age, 0),
      limits: limits(),
      ...logMultiples(),
      young: num(Math.max(Math.floor(age / 3), 1), 0),
      old: num(age + 30, 0),
      yesAmount: money(limit * Math.exp(raw('x_kesin')), currency),
    };
  },
  R09: ({ raw, num, money, limits, firstLimit, list, pct }, { channel }) => {
    const [currency, limit] = firstLimit();
    return {
      window: num(raw('window_days', 7)),
      baseline: num(raw('baseline_days')),
      channels: list('cash_channels').map(channel).join(', '),
      limits: limits(),
      pe: pct(raw('x_esik')),
      pk: pct(raw('x_kesin')),
      yesShare: pct(Math.min(0.1 + raw('x_kesin'), 1)),
      limitOver: money(limit * 1.5, currency),
      limitUnder: money(limit * 0.5, currency),
    };
  },
  R10: ({ raw, num, money, limits, firstLimit, pct }) => {
    const [currency, limit] = firstLimit();
    const low = raw('ratio_low');
    const high = raw('ratio_high');
    const incoming = limit * 2;
    const ratio = Math.min(Math.max(0.95, low), high);
    return {
      hours: num(raw('window_hours'), 0),
      limits: limits(),
      low: pct(low),
      high: pct(high),
      se: pct(raw('x_esik')),
      sk: pct(raw('x_kesin')),
      inAmount: money(incoming, currency),
      outAmount: money(incoming * ratio, currency),
    };
  },
  R11: ({ raw, num }) => ({ window: num(raw('window_days', 7)), xe: num(raw('x_esik'), 0), xk: num(raw('x_kesin'), 0) }),
  R12: ({ raw, num, anchors }) => {
    const multiplier = raw('cv_multiplier');
    return {
      window: num(raw('window_days', 7)),
      cv: num(raw('cv_threshold')),
      mult: num(multiplier),
      ...anchors(),
      yesCount: num(Math.max(1, Math.ceil(raw('x_kesin') / Math.max(multiplier, 1))), 0),
    };
  },
  R13: ({ raw, num, pct }) => {
    const step = raw('max_step_hours');
    const middle = (raw('decay_low') + raw('decay_high')) / 2;
    const first = 100_000;
    return {
      window: num(raw('window_days', 7)),
      step: num(step, 0),
      dl: pct(raw('decay_low')),
      dh: pct(raw('decay_high')),
      depth: num(raw('max_depth'), 0),
      xe: num(raw('x_esik'), 0),
      xk: num(raw('x_kesin'), 0),
      a1: num(first, 0),
      a2: num(Math.round(first * middle), 0),
      a3: num(Math.round(first * middle * middle), 0),
      gap: num(Math.max(1, Math.floor(step / 2)), 0),
      longGap: num(step * 2, 0),
    };
  },
  R14: ({ raw, num, pct }) => {
    const tolerance = raw('pingpong_tolerance');
    const sent = 50_000;
    return {
      window: num(raw('window_days', 7)),
      cycle: num(raw('max_cycle_length'), 0),
      retained: pct(raw('min_retained')),
      tol: pct(tolerance),
      xe: num(raw('x_esik'), 0),
      xk: num(raw('x_kesin'), 0),
      sent: num(sent, 0),
      back: num(Math.round(sent * (1 - tolerance / 2)), 0),
      backFar: num(Math.round(sent * (1 - Math.min(tolerance * 2 + 0.1, 0.9))), 0),
    };
  },
  R15: ({ raw, num }) => ({ window: num(raw('window_days', 7)), gamma: num(raw('gamma')) }),
  R16: ({ raw, num, money, limits, firstLimit, list, logMultiples }) => {
    const [currency, limit] = firstLimit();
    const countries = list('countries');
    return {
      window: num(raw('window_days', 7)),
      countries: countries.join(', '),
      country: countries[0]!,
      limits: limits(),
      ...logMultiples(),
      yesAmount: money(limit * Math.exp(raw('x_kesin')), currency),
    };
  },
  R17: ({ raw, num, list }, { status }) => {
    const minimum = raw('min_rules');
    const excluded = list('excluded_rules', ['R02', 'R17', 'R18']);
    const examples = ['R03', 'R11', 'R12', 'R05', 'R06', 'R07', 'R08', 'R09', 'R10', 'R13']
      .filter((code) => !excluded.includes(code))
      .slice(0, Math.max(2, minimum));
    return {
      window: num(raw('window_days', 30)),
      min: num(minimum, 0),
      excluded: excluded.join(', '),
      statuses: list('open_statuses', ['new', 'in_review']).map(status).join(', '),
      examples: examples.join(', '),
    };
  },
  R18: ({ raw, num }) => ({ p: num(raw('p', 4)), threshold: num(raw('alert_threshold', 0.5)) }),
  S1: ({ raw, num, money, limits, firstLimit, pct }) => {
    const [currency, limit] = firstLimit();
    const unit = raw('round_unit');
    const round = (Math.floor(limit / unit) + 1) * unit;
    return {
      window: num(raw('window_days', 30)),
      limits: limits(),
      unit: num(unit),
      min: num(raw('min_count'), 0),
      se: pct(raw('x_esik')),
      sk: pct(raw('x_kesin')),
      roundEx: money(round, currency),
      oddEx: money(round + Math.min(unit * 0.37, 99.37), currency),
    };
  },
  S2: ({ raw, num, anchors }) => ({ window: num(raw('window_days', 30)), ...anchors() }),
};

/**
 * Interpolation values for one rule and customer type, or null when a required
 * parameter is missing (the rule cannot be explained with invented numbers).
 */
export function explainVars(code: string, values: RuleValues, context: Context): ExplainVars | null {
  if (!isExplained(code)) return null;
  try {
    return BUILDERS[code](makeHelpers(values, context), context);
  } catch (error) {
    if (error instanceof Missing) return null;
    throw error;
  }
}
