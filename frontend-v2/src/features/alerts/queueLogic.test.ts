import { compareRuleCodes } from '@/api/schemas/alerts';
import { daysAgo, queueAlerts } from '@/test/alertData';
import { DEFAULT_FILTERS, hasInvalidRange, parseFilters, toApiQuery, toSearchParams } from './filters';
import { ageInDays, groupAlertsByCustomer, matchesSearch } from './grouping';

describe('queue filters', () => {
  it('defaults to new alerts over all time', () => {
    expect(parseFilters(new URLSearchParams())).toEqual(DEFAULT_FILTERS);
    expect(toApiQuery(DEFAULT_FILTERS, new Date())).toEqual({
      status: 'new',
      severity: undefined,
      rule_code: undefined,
    });
  });

  it('round-trips through the URL and drops defaults', () => {
    const filters = { ...DEFAULT_FILTERS, status: 'all' as const, severity: 'high' as const, rule: 'R03', q: 'ahmet' };
    const params = toSearchParams(filters);
    expect(params.toString()).toBe('status=all&severity=high&rule=R03&q=ahmet');
    expect(parseFilters(params)).toEqual(filters);
    expect(toSearchParams(DEFAULT_FILTERS).toString()).toBe('');
  });

  it('ignores invalid URL values', () => {
    const parsed = parseFilters(new URLSearchParams('status=bogus&severity=x&range=year&from=2026-13'));
    expect(parsed.status).toBe('new');
    expect(parsed.severity).toBe('all');
    expect(parsed.range).toBe('all');
    expect(parsed.from).toBe('');
  });

  it('turns date presets into inclusive created_at windows', () => {
    const today = new Date(2026, 10, 3);
    expect(toApiQuery({ ...DEFAULT_FILTERS, range: 'today' }, today).date_from).toBe('2026-11-03');
    expect(toApiQuery({ ...DEFAULT_FILTERS, range: '7d' }, today).date_from).toBe('2026-10-28');
    expect(toApiQuery({ ...DEFAULT_FILTERS, range: '30d' }, today).date_from).toBe('2026-10-05');
    expect(toApiQuery({ ...DEFAULT_FILTERS, range: 'custom', from: '2026-10-01', to: '2026-10-10' }, today)).toMatchObject({
      date_from: '2026-10-01',
      date_to: '2026-10-10',
    });
  });

  it('flags a custom range that ends before it starts', () => {
    expect(hasInvalidRange({ ...DEFAULT_FILTERS, range: 'custom', from: '2026-10-10', to: '2026-10-01' })).toBe(true);
    expect(hasInvalidRange({ ...DEFAULT_FILTERS, range: '7d', from: '2026-10-10', to: '2026-10-01' })).toBe(false);
  });
});

describe('customer grouping', () => {
  const groups = groupAlertsByCustomer(queueAlerts, new Date());

  it('groups by customer, sorted by severity then oldest alert', () => {
    expect(groups.map((group) => group.customerName)).toEqual([
      'Ahmet Yılmaz',
      'Kaya Tekstil Ltd. Şti.',
      'Selin Arslan',
      'Mert Demir',
      'Burak Aydın',
    ]);
  });

  it('summarises each group', () => {
    const ahmet = groups[0]!;
    expect(ahmet.alerts.map((alert) => alert.alert_id)).toEqual([5518, 5524, 5531]);
    expect(ahmet.ruleCodes).toEqual(['R01', 'R02', 'R03']);
    expect(ahmet.maxSeverity).toBe('high');
    expect(ahmet.ageDays).toBe(4);
    expect(groups[4]!.ageDays).toBe(9);
  });

  it('counts whole calendar days', () => {
    const now = new Date(2026, 10, 3, 0, 5);
    expect(ageInDays('2026-11-02T23:59:00', now)).toBe(1);
    expect(ageInDays('2026-11-03T00:01:00', now)).toBe(0);
  });

  it('searches number or name, ignoring Turkish case', () => {
    const ahmet = groups[0]!;
    expect(matchesSearch(ahmet, 'YILMAZ')).toBe(true);
    expect(matchesSearch(ahmet, 'c-1042')).toBe(true);
    expect(matchesSearch(ahmet, 'selin')).toBe(false);
    expect(matchesSearch(groups[2]!, 'SELİN')).toBe(true);
  });

  it('sorts rule codes naturally with legacy codes last', () => {
    expect(['R10', 'R1', 'R02', 'R4', 'R01'].sort(compareRuleCodes)).toEqual(['R01', 'R02', 'R10', 'R1', 'R4']);
  });

  it('builds test timestamps in local time', () => {
    expect(daysAgo(0)).toMatch(/^\d{4}-\d{2}-\d{2}T10:12:00$/);
  });
});
