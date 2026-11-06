import { isoDate } from '@/utils/format';

export type DayKind = 'today' | 'weekend' | 'weekday';

/** Weekend = Saturday/Sunday of the calendar date (no time zone shift). */
export function dayKind(date: string, today: string = isoDate(new Date())): DayKind {
  if (date === today) return 'today';
  const [year, month, day] = date.split('-').map(Number);
  const weekday = new Date(year!, month! - 1, day!).getDay();
  return weekday === 0 || weekday === 6 ? 'weekend' : 'weekday';
}
