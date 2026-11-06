import { Search, X } from 'lucide-react';
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useAccounts, useCustomers } from '@/features/customers/api';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { Spinner } from '@/components/ui/Spinner';
import { cn } from '@/utils/cn';
import type { FocusOption } from './summary';

const RESULT_LIMIT = 8;
const riskTone: Record<string, 'danger' | 'warning' | 'neutral'> = { high: 'danger', medium: 'warning', low: 'neutral' };

function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** Account numbers are only searched when the text looks like one: every /accounts call is audit-logged. */
const looksLikeAccount = (text: string) => /^tr\d{2,}/i.test(text) || /^\d{6,}$/.test(text);

/**
 * Server-side search over all customers (and accounts by number). After a
 * customer is chosen its accounts appear as chips to narrow the view.
 */
export function FocusPicker({
  focus,
  onChange,
}: {
  focus: FocusOption | null;
  onChange: (focus: FocusOption | null) => void;
}) {
  const { t } = useTranslation();
  const listId = useId();
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const wrapper = useRef<HTMLDivElement>(null);
  const q = useDebounced(text.trim());
  const searching = q.length >= 2;

  const customers = useCustomers({ q, limit: RESULT_LIMIT }, searching);
  const accounts = useAccounts({ q, limit: RESULT_LIMIT }, searching && looksLikeAccount(q));
  // The chosen customer's accounts, for the narrowing chips.
  const customerNo = focus?.type === 'customer' ? focus.id : (focus?.customerNo ?? '');
  const ownAccounts = useAccounts({ customer_no: customerNo, limit: 50 }, Boolean(customerNo));

  const results: FocusOption[] = searching
    ? [
        ...(customers.data?.items ?? []).map((item) => ({
          type: 'customer' as const,
          id: item.customer_no,
          name: item.full_name,
          customerType: item.customer_type,
          risk: item.risk_level,
          openAlerts: item.open_alert_count,
          accountCount: item.account_count,
        })),
        ...(looksLikeAccount(q) ? (accounts.data?.items ?? []) : []).map((item) => ({
          type: 'account' as const,
          id: item.account_no,
          name: item.customer_name,
          customerNo: item.customer_no,
          currency: item.currency,
        })),
      ]
    : [];

  useEffect(() => setActive(0), [q]);
  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (wrapper.current && !wrapper.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const choose = (option: FocusOption) => {
    onChange(option);
    setText('');
    setOpen(false);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!open || results.length === 0) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((index) => Math.min(results.length - 1, index + 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((index) => Math.max(0, index - 1));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      choose(results[active]!);
    } else if (event.key === 'Escape') {
      setOpen(false);
    }
  };
  const loading = searching && (customers.isFetching || accounts.isFetching);

  return (
    <div className="space-y-3">
      <div ref={wrapper} className="relative max-w-xl">
        <label className="mb-1.5 block text-[13px] font-medium" htmlFor={`${listId}-input`}>
          {t('txAnalysis.pickerLabel')}
        </label>
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" aria-hidden />
          <Input
            id={`${listId}-input`}
            role="combobox"
            aria-expanded={open && searching}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={open && results[active] ? `${listId}-${active}` : undefined}
            className="pl-9"
            placeholder={t('txAnalysis.pickerPlaceholder')}
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
            autoComplete="off"
          />
          {loading && <Spinner className="absolute top-1/2 right-3 size-4 -translate-y-1/2" />}
        </div>
        {open && searching && (
          <ul
            id={listId}
            role="listbox"
            className="absolute z-20 mt-1 max-h-80 w-full overflow-y-auto rounded-md border border-border bg-surface py-1 shadow-lg"
          >
            {results.length === 0 && !loading && (
              <li className="px-3 py-2 text-[13px] text-muted">{t('txAnalysis.pickerNoResults')}</li>
            )}
            {results.map((option, index) => (
              <li
                key={`${option.type}:${option.id}`}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={index === active}
                className={cn(
                  'flex cursor-pointer items-center justify-between gap-3 px-3 py-2 text-[13px]',
                  index === active && 'bg-surface-muted',
                )}
                onMouseEnter={() => setActive(index)}
                onMouseDown={(event) => {
                  event.preventDefault();
                  choose(option);
                }}
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">{option.name}</span>
                  <span className="block text-xs text-muted">
                    {option.type === 'customer'
                      ? `${option.id} · ${option.customerType === 'KURUMSAL' ? t('customerType.KURUMSAL') : option.customerType === 'BIREYSEL' ? t('customerType.BIREYSEL') : t('customerType.unknown')} · ${t('txAnalysis.pickerAccounts', { count: option.accountCount ?? 0 })}`
                      : `${t('txAnalysis.pickerAccount')} ${option.id} · ${option.currency} · ${option.customerNo}`}
                  </span>
                </span>
                <span className="flex shrink-0 gap-1.5">
                  {option.openAlerts ? <Badge tone="danger">{t('txAnalysis.pickerAlerts', { count: option.openAlerts })}</Badge> : null}
                  {option.risk && (
                    <Badge tone={riskTone[option.risk] ?? 'neutral'}>
                      {t('txAnalysis.pickerRisk', { level: t(`customerContext.riskLevels.${option.risk}`, option.risk) })}
                    </Badge>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {focus && (
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="font-medium">{focus.name}</span>
          <span className="text-muted">{focus.type === 'customer' ? focus.id : focus.customerNo}</span>
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-muted hover:bg-surface-muted"
            onClick={() => onChange(null)}
          >
            <X className="size-3.5" aria-hidden />
            {t('txAnalysis.pickerClear')}
          </button>
          {(ownAccounts.data?.items.length ?? 0) > 1 && (
            <span className="flex flex-wrap gap-1.5" role="group" aria-label={t('txAnalysis.pickerNarrow')}>
              <Chip active={focus.type === 'customer'} onClick={() => onChange({ type: 'customer', id: customerNo, name: focus.name })}>
                {t('txAnalysis.pickerAllAccounts')}
              </Chip>
              {ownAccounts.data!.items.map((account) => (
                <Chip
                  key={account.account_no}
                  active={focus.type === 'account' && focus.id === account.account_no}
                  onClick={() =>
                    onChange({ type: 'account', id: account.account_no, name: focus.name, customerNo, currency: account.currency })
                  }
                >
                  …{account.account_no.slice(-4)} · {account.currency}
                </Chip>
              ))}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'rounded-full border px-2.5 py-0.5 text-xs font-medium',
        active ? 'border-accent bg-accent/10 text-fg' : 'border-border text-muted hover:bg-surface-muted',
      )}
    >
      {children}
    </button>
  );
}
