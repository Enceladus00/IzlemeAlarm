import { RotateCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useErrorMessage } from '@/utils/errors';
import { Button } from './Button';
import { InlineAlert } from './InlineAlert';

/** Standard rendering of a failed request: translated message, server detail, retry. */
export function ErrorState({
  error,
  onRetry,
  title,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const { message, detail } = useErrorMessage(error);
  return (
    <InlineAlert tone="danger" title={title ?? t('errors.genericTitle')} className={className} live>
      <p>{message}</p>
      {detail && (
        <details className="mt-1 text-xs text-muted">
          <summary className="cursor-pointer">{t('common.details')}</summary>
          <p className="mt-1 font-mono break-words">{detail}</p>
        </details>
      )}
      {onRetry && (
        <Button size="sm" className="mt-2" onClick={onRetry}>
          <RotateCw className="size-3.5" aria-hidden />
          {t('common.retry')}
        </Button>
      )}
    </InlineAlert>
  );
}
