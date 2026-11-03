import { forwardRef, type InputHTMLAttributes } from 'react';
import { cn } from '@/utils/cn';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return (
      <input
        ref={ref}
        className={cn(
          'h-10 w-full rounded-md border border-border-strong bg-surface px-3 text-sm text-fg',
          'placeholder:text-subtle disabled:cursor-not-allowed disabled:opacity-60',
          'aria-[invalid=true]:border-danger',
          className,
        )}
        {...props}
      />
    );
  },
);
