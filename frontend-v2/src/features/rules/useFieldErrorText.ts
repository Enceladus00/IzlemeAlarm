import { useTranslation } from 'react-i18next';
import { formatNumber } from '@/utils/format';
import type { FieldError } from './model';

/** Translates a model FieldError into a message. */
export function useFieldErrorText() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  return (error: FieldError | undefined): string | undefined => {
    if (!error) return undefined;
    switch (error.key) {
      case 'min':
        return t('rules.errors.min', { min: formatNumber(error.min, language, { maximumFractionDigits: 6 }) });
      case 'max':
        return t('rules.errors.max', { max: formatNumber(error.max, language, { maximumFractionDigits: 6 }) });
      case 'limitCurrencyMissing':
      case 'limitCurrencyInvalid':
        return t(`rules.errors.${error.key}`, { row: error.row });
      case 'limitDuplicate':
      case 'limitAmount':
        return t(`rules.errors.${error.key}`, { currency: error.currency });
      default:
        return t(`rules.errors.${error.key}`);
    }
  };
}
