import { z } from 'zod';

/**
 * Python Decimal values are serialized by FastAPI/pydantic as JSON strings
 * ("45000.00"). Accept a number too, but keep the exact decimal string so
 * amounts are never rounded through floating point before display.
 */
export const decimal = z.union([z.string(), z.number()]).transform((value) => String(value));

/** Naive ISO timestamps (no timezone) as produced by the API. */
export const apiDateTime = z.string();

export function pageSchema<T extends z.ZodType>(item: T) {
  return z.object({ total: z.number().int().nonnegative(), items: z.array(item) });
}
