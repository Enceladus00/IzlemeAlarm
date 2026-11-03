import { forwardRef, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react';
import { cn } from '@/utils/cn';

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, ...props },
  ref,
) {
  return (
    <select
      ref={ref}
      className={cn(
        'h-10 w-full rounded-md border border-border-strong bg-surface px-3 text-sm text-fg',
        'disabled:cursor-not-allowed disabled:opacity-60 aria-[invalid=true]:border-danger',
        className,
      )}
      {...props}
    />
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return (
      <textarea
        ref={ref}
        className={cn(
          'min-h-24 w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-fg',
          'placeholder:text-subtle disabled:cursor-not-allowed disabled:opacity-60 aria-[invalid=true]:border-danger',
          className,
        )}
        {...props}
      />
    );
  },
);
