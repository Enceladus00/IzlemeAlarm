import { ruleByCode } from '@/test/ruleData';
import { buildRuleUpdate, draftFromRule, type RuleDraft } from './model';

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
    const { errors, payload } = buildRuleUpdate(ruleByCode('R02'), draftFromRule(ruleByCode('R02')));
    expect(errors).toEqual({});
    expect(payload).toEqual({
      is_active: false,
      weight: 0.45,
      thresholds: {
        BIREYSEL: { status: 'APPROVED', values: { limits: { TRY: 50000 } } },
        KURUMSAL: { status: 'UNSET', values: {} },
      },
    });
  });

  it('builds a complete R01 payload', () => {
    const rule = ruleByCode('R01');
    const draft = withType(draftFromRule(rule), 'BIREYSEL', {
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
    const base = draftFromRule(rule);
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
    const base = draftFromRule(rule);
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
    const base13 = draftFromRule(r13);
    expect(buildRuleUpdate(r13, withType(base13, 'BIREYSEL', { cashAccounts: '3, x' })).errors['BIREYSEL.cash_accounts']).toEqual({ key: 'cashAccounts' });
    expect(buildRuleUpdate(r13, withType(base13, 'BIREYSEL', { cashAccounts: '3, 3' })).errors['BIREYSEL.cash_accounts']).toEqual({ key: 'cashAccountsUnique' });
    expect(buildRuleUpdate(r13, withType(base13, 'BIREYSEL', { cashAccounts: '' })).payload!.thresholds.BIREYSEL.values.cash_accounts).toEqual([]);

    const r03 = ruleByCode('R03');
    const draft03 = withType(draftFromRule(r03), 'KURUMSAL', { status: 'APPROVED' });
    expect(buildRuleUpdate(r03, draft03).errors['KURUMSAL.cash_channels']).toEqual({ key: 'channelsRequired' });

    const r06 = ruleByCode('R06');
    const draft06 = withType(draftFromRule(r06), 'BIREYSEL', {
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
    const { errors } = buildRuleUpdate(rule, { ...draftFromRule(rule), isActive: true, weight: '1.5' });
    expect(errors.active).toEqual({ key: 'required' });
    expect(errors.weight).toEqual({ key: 'max', max: 1 });
  });
});
