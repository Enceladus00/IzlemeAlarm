import 'i18next';
import type { Translation } from './locales/tr';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: { translation: Translation };
    returnNull: false;
  }
}
