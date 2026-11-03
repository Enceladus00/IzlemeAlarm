import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';
import { cn } from '@/utils/cn';

export interface TabItem<T extends string> {
  value: T;
  label: ReactNode;
  content: ReactNode;
}

/** WAI-ARIA tabs: arrow keys / Home / End move between tabs (manual roving focus). */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  const baseId = useId();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const activeIndex = Math.max(0, items.findIndex((item) => item.value === value));

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    let next = activeIndex;
    if (event.key === 'ArrowRight') next = (activeIndex + 1) % items.length;
    else if (event.key === 'ArrowLeft') next = (activeIndex - 1 + items.length) % items.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = items.length - 1;
    else return;
    event.preventDefault();
    onChange(items[next]!.value);
    refs.current[next]?.focus();
  };

  const active = items[activeIndex];
  return (
    <div>
      <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="flex gap-1 overflow-x-auto border-b border-border">
        {items.map((item, index) => {
          const selected = index === activeIndex;
          return (
            <button
              key={item.value}
              ref={(element) => {
                refs.current[index] = element;
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${item.value}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${item.value}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(item.value)}
              className={cn(
                '-mb-px border-b-2 px-4 py-2.5 text-[13px] font-semibold whitespace-nowrap',
                selected ? 'border-accent text-fg' : 'border-transparent text-muted hover:text-fg',
              )}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {active && (
        <div role="tabpanel" id={`${baseId}-panel-${active.value}`} aria-labelledby={`${baseId}-tab-${active.value}`} className="pt-4">
          {active.content}
        </div>
      )}
    </div>
  );
}
