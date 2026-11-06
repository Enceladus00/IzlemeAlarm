import { dayKind } from './dayKind';

describe('dayKind (E10 daily chart)', () => {
  it('marks today, weekends and weekdays by calendar date', () => {
    expect(dayKind('2026-11-06', '2026-11-06')).toBe('today');
    expect(dayKind('2026-11-07', '2026-11-06')).toBe('weekend'); // Saturday
    expect(dayKind('2026-11-08', '2026-11-06')).toBe('weekend'); // Sunday
    expect(dayKind('2026-11-09', '2026-11-06')).toBe('weekday'); // Monday
  });
});
