import en from '@/i18n/locales/en';
import tr from '@/i18n/locales/tr';
import { EXPLAINED_RULES, explainVars, parameterDefault, type RuleValues } from './explain';

const context = { language: 'tr', channel: (code: string) => code.toUpperCase(), status: (code: string) => code };

/** Plausible saved values for every rule (as the API returns them: decimals as strings). */
const SAMPLE: Record<(typeof EXPLAINED_RULES)[number], RuleValues> = {
  R01: { limits: { TRY: '10000.0' }, x_esik: 2, x_kesin: 4, minimum_income_ratio: '0.55', income_currency: 'TRY' },
  R02: { limits: { TRY: '50000.0', USD: '2000' } },
  R03: { limits: { TRY: '10000' }, x_esik: 3, x_kesin: 6, cash_channels: ['atm', 'branch'], window_days: 7 },
  R04: { window_days: 30, x_esik: '2', x_kesin: '5' },
  R05: { history_days: 180, kappa: '5', mad_floor: '0.1', income_bands: 5, x_esik: '3', x_kesin: '6' },
  R06: { history_weeks: 8, min_count: 10, x_esik: '3', x_kesin: '8' },
  R07: { dormant_days: 180, window_days: 7, limits: { TRY: '20000' }, x_esik: '0', x_kesin: '1.5' },
  R08: { account_age_days: 90, limits: { TRY: '50000' }, x_esik: '0', x_kesin: '1' },
  R09: { window_days: 30, baseline_days: 90, cash_channels: ['atm'], limits: { TRY: '10000' }, x_esik: '0.2', x_kesin: '0.5' },
  R10: { window_hours: 48, limits: { TRY: '20000' }, ratio_low: '0.8', ratio_high: '1.2', x_esik: '0.5', x_kesin: '0.9' },
  R11: { window_days: 7, x_esik: 5, x_kesin: 10 },
  R12: { window_days: 7, cv_threshold: '0.1', cv_multiplier: '1.5', x_esik: '5', x_kesin: '10' },
  R13: { window_days: 7, max_step_hours: 24, decay_low: '0.8', decay_high: '0.99', max_depth: 10, x_esik: 3, x_kesin: 5 },
  R14: { window_days: 30, max_cycle_length: 5, min_retained: '0.8', pingpong_tolerance: '0.1', x_esik: 2, x_kesin: 4 },
  R15: { window_days: 90, suspicious_status: 'confirmed_suspicious', gamma: '0.6' },
  R16: { countries: ['IR', 'KP'], limits: { TRY: '10000' }, window_days: 30, x_esik: '0', x_kesin: '1' },
  R17: { window_days: 30, min_rules: 3 },
  R18: {},
  S1: { limits: { TRY: '10000' }, round_unit: '1000', min_count: 3, x_esik: '0.5', x_kesin: '0.9' },
  S2: { mad_floor: '0.1', x_esik: '3', x_kesin: '5' },
};

function interpolate(template: string, vars: Record<string, string>) {
  return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) => vars[name] ?? `{{${name}}}`);
}

describe('rule explanations (E09)', () => {
  it.each(EXPLAINED_RULES)('%s fills every placeholder in both languages', (code) => {
    const vars = explainVars(code, SAMPLE[code], context);
    expect(vars).not.toBeNull();
    for (const locale of [tr, en]) {
      for (const part of ['sentence', 'yes', 'no'] as const) {
        const text = interpolate(locale.ruleText[code][part], vars!);
        expect(text, `${code}.${part}`).not.toMatch(/\{\{|NaN|undefined|Infinity/);
      }
    }
  });

  it('uses the current parameters in the sentence', () => {
    const vars = explainVars('R01', SAMPLE.R01, context)!;
    expect(interpolate(tr.ruleText.R01.sentence, vars)).toContain('9.000 TRY ile 10.000 TRY arasında');
    expect(vars).toMatchObject({ window: '7', xe: '2', xk: '4', ratio: '55', above: '11.000 TRY' });
    expect(explainVars('R03', SAMPLE.R03, context)!.channels).toBe('ATM, BRANCH');
    expect(explainVars('R18', {}, context)).toEqual({ p: '4', threshold: '0,5' });
  });

  it('shows log-ratio anchors as multiples of the reference amount', () => {
    expect(explainVars('R16', SAMPLE.R16, context)).toMatchObject({ me: '1', mk: '2,72' });
  });

  it('returns null instead of inventing a missing required value', () => {
    expect(explainVars('R02', {}, context)).toBeNull();
    expect(explainVars('R01', { limits: { TRY: '500' } }, context)).toBeNull();
    expect(explainVars('R1', {}, context)).toBeNull();
  });

  it('knows the backend defaults shown next to unset optional parameters', () => {
    expect(parameterDefault('R01', 'window_days')).toBe(7);
    expect(parameterDefault('S1', 'window_days')).toBe(30);
    expect(parameterDefault('R01', 'band_low')).toBe(0.9);
    expect(parameterDefault('R01', 'limits')).toBeUndefined();
  });
});
