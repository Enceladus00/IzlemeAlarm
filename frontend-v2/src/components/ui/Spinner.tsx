import { cn } from '@/utils/cn';

export function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <span
      role={label ? 'status' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn(
        'inline-block size-5 animate-spin rounded-full border-2 border-current border-r-transparent',
        className,
      )}
    />
  );
}

export function PageSpinner({ label }: { label: string }) {
  return (
    <div className="flex min-h-[40vh] items-center justify-center text-muted">
      <Spinner className="size-7" label={label} />
    </div>
  );
}
