import * as Popover from '@radix-ui/react-popover';
import { Check, ChevronDown } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';
import { cn } from '@/utils/cn';

export interface FilterOption<T extends string> {
  value: T;
  label: ReactNode;
}

/**
 * A pill that shows "Label: Value" and opens a single-choice list. Uses
 * native radio inputs so keyboard and screen-reader behaviour is standard.
 */
export function FilterChip<T extends string>({
  label,
  value,
  options,
  onChange,
  active,
  footer,
}: {
  label: string;
  value: T;
  options: FilterOption<T>[];
  onChange: (value: T) => void;
  /** Dark "applied" styling; defaults to value !== first option. */
  active?: boolean;
  /** Extra content under the options (e.g. custom date inputs). */
  footer?: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const name = useId();
  const selected = options.find((option) => option.value === value);
  const isActive = active ?? value !== options[0]?.value;

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className={cn(
            'inline-flex h-9 items-center gap-1.5 rounded-full border px-4 text-[13px] font-medium whitespace-nowrap transition-colors',
            isActive
              ? 'border-transparent bg-fg text-surface'
              : 'border-border-strong bg-surface text-fg hover:bg-surface-hover',
          )}
        >
          <span>
            {label}: {selected?.label ?? value}
          </span>
          <ChevronDown className="size-3.5 opacity-70" aria-hidden />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          className="z-50 max-h-[70vh] min-w-52 overflow-y-auto rounded-lg border border-border bg-surface p-1.5 text-[13px] text-fg shadow-lg"
        >
          <fieldset>
            <legend className="sr-only">{label}</legend>
            {options.map((option) => {
              const checked = option.value === value;
              return (
                <label
                  key={option.value}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 hover:bg-surface-hover has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-focus"
                >
                  <input
                    type="radio"
                    name={name}
                    className="sr-only"
                    checked={checked}
                    onChange={() => {
                      onChange(option.value);
                      if (!footer) setOpen(false);
                    }}
                  />
                  <Check className={cn('size-4 shrink-0', checked ? 'opacity-100' : 'opacity-0')} strokeWidth={3} aria-hidden />
                  <span className={cn(checked && 'font-semibold')}>{option.label}</span>
                </label>
              );
            })}
          </fieldset>
          {footer?.(() => setOpen(false))}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
