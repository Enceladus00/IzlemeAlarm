import { useTranslation } from 'react-i18next';
import { ApiError } from '@/api/client';

/**
 * Turns any thrown value into a translated, user-facing message. The server's
 * own `detail` (always English) is kept separately as a technical detail.
 */
export function useErrorMessage(error: unknown): { message: string; detail: string | null } {
  const { t } = useTranslation();
  if (error instanceof ApiError) {
    return { message: t(`errors.${error.kind}`), detail: error.detail };
  }
  return { message: t('errors.unexpected'), detail: error instanceof Error ? error.message : null };
}
