import { parseApiDate } from '@/utils/format';

/** Whole calendar days between the alert's local date and today (0 = today). */
export function ageInDays(createdAt: string, now: Date): number {
  const created = parseApiDate(createdAt);
  if (!created) return 0;
  const startOfCreated = new Date(created.getFullYear(), created.getMonth(), created.getDate());
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.max(0, Math.round((startOfToday.getTime() - startOfCreated.getTime()) / 86_400_000));
}
