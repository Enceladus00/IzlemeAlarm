import { useTranslation } from 'react-i18next';
import { ApiError } from '@/api/client';

/**
 * K7: the API keeps English `detail` texts; their Turkish wording lives in the
 * locale files under `errors.detail` (exact text) and `errors.detailPrefix`
 * (texts that start with a fixed part, e.g. "Permission required: …").
 * A backend test (tests/test_error_translations.py) fails when a server text
 * has no entry, so a changed message cannot silently lose its translation.
 */
function lookup(
  bundle: unknown,
  detail: string,
): string | null {
  const errors = (bundle as { errors?: { detail?: Record<string, string>; detailPrefix?: Record<string, string> } })?.errors;
  const exact = errors?.detail?.[detail];
  if (exact) return exact;
  for (const [prefix, text] of Object.entries(errors?.detailPrefix ?? {})) {
    if (detail.startsWith(prefix)) return text;
  }
  return null;
}

/** Translated text for a server error: the specific message when known, else by kind. */
export function useServerMessage(): (error: unknown) => string {
  const { t, i18n } = useTranslation();
  return (error: unknown) => {
    if (error instanceof ApiError) {
      const bundle = i18n.getResourceBundle(i18n.resolvedLanguage ?? 'tr', 'translation');
      return (error.detail && lookup(bundle, error.detail)) || t(`errors.${error.kind}`);
    }
    return t('errors.unexpected');
  };
}

/**
 * Turns any thrown value into a translated, user-facing message. The server's
 * own `detail` (always English) is kept separately as a technical detail.
 */
export function useErrorMessage(error: unknown): { message: string; detail: string | null } {
  const { t } = useTranslation();
  const serverMessage = useServerMessage();
  if (error instanceof ApiError) {
    return { message: serverMessage(error), detail: error.detail };
  }
  return { message: t('errors.unexpected'), detail: error instanceof Error ? error.message : null };
}
