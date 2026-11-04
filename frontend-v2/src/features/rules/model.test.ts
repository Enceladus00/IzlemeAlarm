import { ruleByCode } from '@/test/ruleData';
import type { Rule } from '@/api/schemas/rules';
import { buildRuleUpdate, copyIndividualToCorporate, draftFromRule, type RuleDraft } from './model';

/** Drafts with the K5 change reason filled in. */
function reasoned(rule: Rule): RuleDraft {
  return { ...draftFromRule(rule), reason: 'Kurum onayı' };
}

function withType(draft: RuleDraft, type: 'BIREYSEL' | 'KURUMSAL', patch: Partial<RuleDraft['types']['BIREYSEL']>): RuleDraft {
  return { ...draft, types: { ...draft.types, [type]: { ...draft.types[type], ...patch } } };
}

describe('draftFromRule', () => {
  it('loads saved values and leaves spare limit rows', () => {
    const draft = draftFromRule(ruleByCode('R02'));
    expect(draft.weight).toBe('0.450');
    expect(draft.types.BIREYSEL.status).toBe('APPROVED');
    expect(draft.types.BIREYSEL.limits).toEqual([
      { currency: 'TRY', amount: '50000.0' },
      { currency: '', amount: '' },
      { currency: '', amount: '' },
    ]);
    expect(draft.types.KURUMSAL.status).toBe('UNSET');
  });

  it('applies only the Streamlit defaults (7-day window, R01 band ratios)', () => {
    expect(draftFromRule(ruleByCode('R03')).types.BIREYSEL.numbers).toEqual({ x_esik: '', x_kesin: '', window_days: '7' });
    const r01 = draftFromRule(ruleByCode('R01')).types.KURUMSAL.numbers;
    expect([r01.band_low, r01.above_check, r01.minimum_income_ratio]).toEqual(['0.9', '1.1', '']);
  });

  it('restores account lists and season factors as text', () => {
    expect(draftFromRule(ruleByCode('R13')).types.BIREYSEL.cashAccounts).toBe('3, 9');
  });
});

describe('buildRuleUpdate', () => {
  it('sends UNSET types with empty values and converts numbers', () => {
    const { errors, payload } = buildRuleUpdate(ruleByCode('R02'), reasoned(ruleByCode('R02')));
    expect(errors).toEqual({});
    expect(payload).toEqual({
      is_active: false,
      weight: 0.45,
      thresholds: {
        BIREYSEL: { status: 'APPROVED', values: { limits: { TRY: 50000 } } },
        KURUMSAL: { status: 'UNSET', values: {} },
      },
      reason: 'Kurum onayı',
    });
  });

  it('builds a complete R01 payload', () => {
    const rule = ruleByCode('R01');
    const draft = withType(reasoned(rule), 'BIREYSEL', {
      status: 'PROVISIONAL',
      limits: [{ currency: 'try', amount: '10000' }],
      numbers: { x_esik: '2', x_kesin: '5', window_days: '7', band_low: '0.9', above_check: '1.1', minimum_income_ratio: '0.45' },
      incomeCurrency: 'try',
    });
    expect(buildRuleUpdate(rule, draft).payload!.thresholds.BIREYSEL).toEqual({
      status: 'PROVISIONAL',
      values: {
        limits: { TRY: 10000 },
        window_days: 7,
        x_esik: 2,
        x_kesin: 5,
        band_low: 0.9,
        above_check: 1.1,
        minimum_income_ratio: 0.45,
        income_currency: 'TRY',
      },
    });
  });

  it('reports limit-row problems like Streamlit', () => {
    const rule = ruleByCode('R02');
    const base = reasoned(rule);
    const errorsFor = (limits: Array<{ currency: string; amount: string }>) =>
      buildRuleUpdate(rule, withType(base, 'BIREYSEL', { limits })).errors;
    expect(errorsFor([{ currency: '', amount: '5' }])['BIREYSEL.limits.0']).toEqual({ key: 'limitCurrencyMissing', row: 1 });
    expect(errorsFor([{ currency: 'TL', amount: '5' }])['BIREYSEL.limits.0']).toEqual({ key: 'limitCurrencyInvalid', row: 1 });
    expect(errorsFor([{ currency: 'TRY', amount: '5' }, { currency: 'TRY', amount: '6' }])['BIREYSEL.limits.1']).toEqual({ key: 'limitDuplicate', currency: 'TRY' });
    expect(errorsFor([{ currency: 'USD', amount: '0' }])['BIREYSEL.limits.0']).toEqual({ key: 'limitAmount', currency: 'USD' });
    expect(errorsFor([{ currency: '', amount: '' }])['BIREYSEL.limits']).toEqual({ key: 'limitsRequired' });
  });

  it('checks anchors, integers and bounds', () => {
    const rule = ruleByCode('R13');
    const base = reasoned(rule);
    const errorsFor = (numbers: Record<string, string>) =>
      buildRuleUpdate(rule, withType(base, 'BIREYSEL', { numbers: { ...base.types.BIREYSEL.numbers, ...numbers } })).errors;
    expect(errorsFor({})).toEqual({});
    expect(errorsFor({ x_esik: '4', x_kesin: '4' })['BIREYSEL.x_kesin']).toEqual({ key: 'anchorsOrder' });
    expect(errorsFor({ x_esik: '1.5' })['BIREYSEL.x_esik']).toEqual({ key: 'integer' });
    expect(errorsFor({ max_depth: '21' })['BIREYSEL.max_depth']).toEqual({ key: 'max', max: 20 });
    expect(errorsFor({ decay_low: '0' })['BIREYSEL.decay_low']).toEqual({ key: 'min', min: 0.000001 });
    expect(errorsFor({ max_step_hours: '' })['BIREYSEL.max_step_hours']).toEqual({ key: 'required' });
  });

  it('validates account lists, channels and season factors', () => {
    const r13 = ruleByCode('R13');
    const base13 = reasoned(r13);
    expect(buildRuleUpdate(r13, withType(base13, 'BIREYSEL', { cashAccounts: '3, x' })).errors['BIREYSEL.cash_accounts']).toEqual({ key: 'cashAccounts' });
    expect(buildRuleUpdate(r13, withType(base13, 'BIREYSEL', { cashAccounts: '3, 3' })).errors['BIREYSEL.cash_accounts']).toEqual({ key: 'cashAccountsUnique' });
    expect(buildRuleUpdate(r13, withType(base13, 'BIREYSEL', { cashAccounts: '' })).payload!.thresholds.BIREYSEL.values.cash_accounts).toEqual([]);

    const r03 = ruleByCode('R03');
    const draft03 = withType(reasoned(r03), 'KURUMSAL', { status: 'APPROVED' });
    expect(buildRuleUpdate(r03, draft03).errors['KURUMSAL.cash_channels']).toEqual({ key: 'channelsRequired' });

    const r06 = ruleByCode('R06');
    const draft06 = withType(reasoned(r06), 'BIREYSEL', {
      status: 'APPROVED',
      numbers: { history_weeks: '4', min_count: '3', x_esik: '1.5', x_kesin: '3' },
    });
    expect(buildRuleUpdate(r06, { ...draft06, types: { ...draft06.types, BIREYSEL: { ...draft06.types.BIREYSEL, seasonFactor: '2026-01-04=1.2\n\n2026-02-01=0.9' } } }).payload!.thresholds.BIREYSEL.values.season_factor).toEqual({
      '2026-01-04': '1.2',
      '2026-02-01': '0.9',
    });
    for (const bad of ['2026-02-30=1.2', '2026-01-04=0', '2026-01-04=1\n2026-01-04=2', 'nonsense']) {
      const result = buildRuleUpdate(r06, { ...draft06, types: { ...draft06.types, BIREYSEL: { ...draft06.types.BIREYSEL, seasonFactor: bad } } });
      expect(result.errors['BIREYSEL.season_factor']).toEqual({ key: 'seasonFactor' });
    }
  });

  it('refuses activation with every type UNSET and a weight outside 0–1', () => {
    const rule = ruleByCode('R03');
    const { errors } = buildRuleUpdate(rule, { ...reasoned(rule), isActive: true, weight: '1.5' });
    expect(errors.active).toEqual({ key: 'required' });
    expect(errors.weight).toEqual({ key: 'max', max: 1 });
  });
});

function newRule(code: string, names: string[]): Rule {
  return {
    rule_code: code,
    name: code,
    description: null,
    is_active: false,
    weight: '1.000',
    thresholds: { BIREYSEL: { status: 'UNSET', values: {} }, KURUMSAL: { status: 'UNSET', values: {} } },
    metadata: {
      steps: [],
      alert_mode: 'ALERT',
      parameters: names.map((name) => ({
        name,
        type: ['window_days', 'min_rules', 'min_count'].includes(name) ? 'integer' : 'decimal',
        unit: '',
        meaning: '',
        required: true,
      })),
      analyst_review_notes: [],
      feasibility: 'HIGH',
      feasibility_reason: '',
    },
  };
}

describe('K5 reason, K11 copy and the new rules', () => {
  it('requires a reason of at most 500 characters', () => {
    const rule = ruleByCode('R02');
    expect(buildRuleUpdate(rule, draftFromRule(rule)).errors.reason).toEqual({ key: 'reasonRequired' });
    expect(buildRuleUpdate(rule, { ...draftFromRule(rule), reason: 'x'.repeat(501) }).errors.reason).toEqual({
      key: 'reasonTooLong',
      max: 500,
    });
    expect(buildRuleUpdate(rule, { ...draftFromRule(rule), reason: '  Onay  ' }).payload!.reason).toBe('Onay');
  });

  it('copies the individual settings to corporate', () => {
    const rule = ruleByCode('R02');
    const copied = copyIndividualToCorporate(draftFromRule(rule));
    expect(copied.types.KURUMSAL).toEqual(copied.types.BIREYSEL);
    copied.types.KURUMSAL.limits[0]!.amount = '1';
    expect(copied.types.BIREYSEL.limits[0]!.amount).not.toBe('1');
  });

  it('validates R16 countries', () => {
    const rule = newRule('R16', ['countries', 'limits', 'window_days', 'x_esik', 'x_kesin']);
    const base = reasoned(rule);
    const draft = (countries: string) =>
      withType(base, 'BIREYSEL', {
        status: 'PROVISIONAL',
        countries,
        limits: [{ currency: 'TRY', amount: '20000' }],
        numbers: { window_days: '30', x_esik: '0', x_kesin: '1.609' },
      });
    expect(buildRuleUpdate(rule, draft('ir, kp')).payload!.thresholds.BIREYSEL.values.countries).toEqual(['IR', 'KP']);
    expect(buildRuleUpdate(rule, draft('IRN')).errors['BIREYSEL.countries']).toEqual({ key: 'countries' });
    expect(buildRuleUpdate(rule, draft('IR, IR')).errors['BIREYSEL.countries']).toEqual({ key: 'countries' });
  });

  it('builds R17 lists and keeps S1 anchors within 0–1', () => {
    const r17 = newRule('R17', ['window_days', 'min_rules', 'excluded_rules', 'open_statuses']);
    const draft17 = withType(reasoned(r17), 'BIREYSEL', { status: 'PROVISIONAL', numbers: { window_days: '30', min_rules: '2' } });
    expect(buildRuleUpdate(r17, draft17).payload!.thresholds.BIREYSEL.values).toEqual({
      window_days: 30,
      min_rules: 2,
      excluded_rules: ['R02', 'R17', 'R18'],
      open_statuses: ['new', 'in_review'],
    });
    expect(buildRuleUpdate(r17, withType(draft17, 'BIREYSEL', { openStatuses: [] })).errors['BIREYSEL.open_statuses']).toEqual({
      key: 'statusesRequired',
    });
    expect(buildRuleUpdate(r17, withType(draft17, 'BIREYSEL', { numbers: { window_days: '30', min_rules: '1' } })).errors['BIREYSEL.min_rules']).toEqual({
      key: 'min',
      min: 2,
    });
    const s1 = newRule('S1', ['limits', 'round_unit', 'min_count', 'window_days', 'x_esik', 'x_kesin']);
    const draftS1 = withType(reasoned(s1), 'BIREYSEL', {
      status: 'PROVISIONAL',
      limits: [{ currency: 'TRY', amount: '10000' }],
      numbers: { round_unit: '1000', min_count: '5', window_days: '30', x_esik: '0.6', x_kesin: '1.5' },
    });
    expect(buildRuleUpdate(s1, draftS1).errors['BIREYSEL.x_kesin']).toEqual({ key: 'max', max: 1 });
  });
});
