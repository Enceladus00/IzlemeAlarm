export type Direction = 'all' | 'incoming' | 'outgoing';

export interface TxFilters {
  customer: string;
  direction: Direction;
  from: string;
  to: string;
  min: string;
  max: string;
}

export const EMPTY_TX_FILTERS: TxFilters = { customer: '', direction: 'all', from: '', to: '', min: '', max: '' };

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function parseTxFilters(params: URLSearchParams): TxFilters {
  const direction = params.get('direction');
  return {
    customer: (params.get('customer') ?? '').trim(),
    direction: direction === 'incoming' || direction === 'outgoing' ? direction : 'all',
    from: ISO_DATE.test(params.get('from') ?? '') ? params.get('from')! : '',
    to: ISO_DATE.test(params.get('to') ?? '') ? params.get('to')! : '',
    min: params.get('min') ?? '',
    max: params.get('max') ?? '',
  };
}

export function txFiltersToParams(filters: TxFilters, focus?: string | null): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.customer.trim()) params.set('customer', filters.customer.trim());
  if (filters.direction !== 'all') params.set('direction', filters.direction);
  if (filters.from) params.set('from', filters.from);
  if (filters.to) params.set('to', filters.to);
  if (filters.min) params.set('min', filters.min);
  if (filters.max) params.set('max', filters.max);
  if (focus) params.set('focus', focus);
  return params;
}

export type TxFilterError = 'errorDateOrder' | 'errorAmountOrder' | 'errorAmountPositive' | 'errorDirection';

/** Same checks as the Streamlit page and the API (amounts must be > 0). */
export function validateTxFilters(filters: TxFilters): Partial<Record<keyof TxFilters, TxFilterError>> {
  const errors: Partial<Record<keyof TxFilters, TxFilterError>> = {};
  if (filters.from && filters.to && filters.from > filters.to) errors.to = 'errorDateOrder';
  const min = filters.min === '' ? null : Number(filters.min);
  const max = filters.max === '' ? null : Number(filters.max);
  if (min !== null && !(min > 0)) errors.min = 'errorAmountPositive';
  if (max !== null && !(max > 0)) errors.max = 'errorAmountPositive';
  if (min !== null && max !== null && min > 0 && max > 0 && min > max) errors.max = 'errorAmountOrder';
  if (filters.direction !== 'all' && !filters.customer.trim()) errors.direction = 'errorDirection';
  return errors;
}

/** Query parameters for GET /transactions (without paging). */
export function toTxQuery(filters: TxFilters) {
  return {
    customer_no: filters.customer.trim() || undefined,
    direction: filters.direction === 'all' ? undefined : filters.direction,
    date_from: filters.from || undefined,
    date_to: filters.to || undefined,
    min_amount: filters.min || undefined,
    max_amount: filters.max || undefined,
  };
}
