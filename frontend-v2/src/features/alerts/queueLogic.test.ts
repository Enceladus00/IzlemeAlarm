import { compareRuleCodes } from '@/api/schemas/alerts';
import { ApiError } from '@/api/client';
import { explanationVariables, fillTemplate } from './explanation';
import {
  ANALYST_DEFAULTS,
  COMPLIANCE_DEFAULTS,
  hasInvalidRange,
  parseFilters,
  toApiQuery,
  toSearchParams,
} from './filters';
import { ageInDays } from './grouping';
import { availableTransitions, isComplianceUser } from './workflow';

describe('queue filters', () => {
  it('defaults to new alerts over all time for analysts', () => {
    expect(parseFilters(new URLSearchParams())).toEqual(ANALYST_DEFAULTS);
    expect(toApiQuery(ANALYST_DEFAULTS, new Date(), 50)).toEqual({
      status: 'new',
      severity: undefined,
      rule_code: undefined,
      q: undefined,
      sort: 'severity_age',
      offset: 0,
      limit: 50,
    });
  });

  it('uses the compliance defaults when given', () => {
    expect(parseFilters(new URLSearchParams(), COMPLIANCE_DEFAULTS)).toMatchObject({ status: 'in_review', sort: 'waiting' });
    expect(toSearchParams(COMPLIANCE_DEFAULTS, COMPLIANCE_DEFAULTS).toString()).toBe('');
  });

  it('round-trips through the URL and drops defaults', () => {
    const filters = { ...ANALYST_DEFAULTS, status: 'in_review' as const, severity: 'high' as const, rule: 'R03', q: 'ahmet', page: 2 };
    const params = toSearchParams(filters);
    expect(params.toString()).toBe('status=in_review&severity=high&rule=R03&q=ahmet&page=3');
    expect(parseFilters(params)).toEqual(filters);
    expect(toApiQuery(filters, new Date(), 50).offset).toBe(100);
  });

  it('ignores invalid URL values', () => {
    const parsed = parseFilters(new URLSearchParams('status=all&severity=x&range=year&from=2026-13&page=-4'));
    expect(parsed.status).toBe('new');
    expect(parsed.severity).toBe('all');
    expect(parsed.range).toBe('all');
    expect(parsed.from).toBe('');
    expect(parsed.page).toBe(0);
  });

  it('turns date presets into inclusive created_at windows', () => {
    const today = new Date(2026, 10, 3);
    expect(toApiQuery({ ...ANALYST_DEFAULTS, range: 'today' }, today, 50).date_from).toBe('2026-11-03');
    expect(toApiQuery({ ...ANALYST_DEFAULTS, range: '7d' }, today, 50).date_from).toBe('2026-10-28');
    expect(toApiQuery({ ...ANALYST_DEFAULTS, range: '30d' }, today, 50).date_from).toBe('2026-10-05');
    expect(hasInvalidRange({ ...ANALYST_DEFAULTS, range: 'custom', from: '2026-10-10', to: '2026-10-01' })).toBe(true);
  });

  it('computes alert age in calendar days', () => {
    expect(ageInDays('2026-11-01T23:59:00', new Date(2026, 10, 3, 0, 1))).toBe(2);
  });

  it('orders rule codes naturally with legacy codes last', () => {
    expect(['R4', 'R10', 'S1', 'R02', 'R1'].sort(compareRuleCodes)).toEqual(['R02', 'R10', 'S1', 'R1', 'R4']);
  });
});

describe('workflow (mirrors backend/services/alert_workflow.py)', () => {
  const analyst = new Set(['alert:view', 'alert:update', 'alert:escalate']);
  const compliance = new Set(['alert:view', 'alert:confirm']);

  it('offers each role only its transitions', () => {
    expect(availableTransitions('new', analyst).map((item) => item.to)).toEqual(['closed', 'in_review']);
    expect(availableTransitions('in_review', analyst)).toEqual([]);
    expect(availableTransitions('new', compliance)).toEqual([]);
    expect(availableTransitions('in_review', compliance).map((item) => item.to)).toEqual([
      'confirmed_suspicious',
      'closed',
      'new',
    ]);
    expect(availableTransitions('closed', compliance)).toEqual([]);
  });

  it('recognises compliance officers', () => {
    expect(isComplianceUser(compliance)).toBe(true);
    expect(isComplianceUser(analyst)).toBe(false);
  });
});

describe('explanation sentences (K8)', () => {
  it('fills placeholders and refuses incomplete sentences', () => {
    expect(fillTemplate('{a} ve {b}', { a: '1', b: '2' })).toBe('1 ve 2');
    expect(fillTemplate('{a} ve {b}', { a: '1' })).toBeNull();
  });

  it('merges parameters and step details and formats shares as percentages', () => {
    const vars = explanationVariables(
      {
        rule_code: 'R09',
        rule_name: 'Nakit',
        alert_mode: 'ALERT',
        customer_type: 'BIREYSEL',
        parameter_status: 'APPROVED',
        raw_x: '0.25',
        score: '0.9',
        x_esik: null,
        x_kesin: null,
        parameters: { window_days: 30 },
        steps: [{ step: 2, text: '', status: 'completed', details: { current_cash_share: '0.6' } }],
        run: { run_id: 'r', as_of: '2026-11-03T00:00:00' },
      },
      'tr',
    );
    expect(vars.window_days).toBe('30');
    expect(vars.current_cash_share_pct).toBe('60');
    expect(vars.x).toBe('0,25');
  });
});

describe('ApiError', () => {
  it('carries the failing alert id', () => {
    expect(new ApiError({ status: 403, kind: 'forbidden', alertId: 7 }).alertId).toBe(7);
  });
});
