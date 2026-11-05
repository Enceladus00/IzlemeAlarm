import type { RulePerformance } from '@/api/schemas/dashboard';

/**
 * "Gözden geçir" (guide v3.0, E07/E10): a rule whose alerts are rarely confirmed
 * deserves a look at its thresholds. 10% over 30 days is the guide's proposal and an
 * open question for the mentor, so both numbers live here.
 */
export const REVIEW_HIT_RATE = 0.1;
/** Too few decided alerts say nothing about a rule's hit rate. */
export const REVIEW_MIN_DECISIONS = 5;
export const REVIEW_PERIOD_DAYS = 30;

export function needsReview(row: Pick<RulePerformance[number], 'hit_rate' | 'confirmed' | 'closed'>): boolean {
  return row.hit_rate !== null && row.confirmed + row.closed >= REVIEW_MIN_DECISIONS && row.hit_rate < REVIEW_HIT_RATE;
}
