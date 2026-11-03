import { Moon, Sun } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { changeLanguage, SUPPORTED_LANGUAGES } from '@/i18n';
import { useTheme } from '@/theme/theme-context';
import { cn } from '@/utils/cn';

export function LanguageSwitcher({ tone = 'sidebar' }: { tone?: 'sidebar' | 'surface' }) {
  const { t, i18n } = useTranslation();
  return (
    <div role="group" aria-label={t('preferences.language')} className="inline-flex rounded-md p-0.5 ring-1 ring-inset ring-current/20">
      {SUPPORTED_LANGUAGES.map((language) => {
        const active = i18n.resolvedLanguage === language;
        return (
          <button
            key={language}
            type="button"
            lang={language}
            aria-pressed={active}
            aria-label={t(`preferences.languages.${language}`)}
            title={t(`preferences.languages.${language}`)}
            onClick={() => void changeLanguage(language)}
            className={cn(
              'rounded px-2 py-1 text-xs font-semibold uppercase',
              active
                ? tone === 'sidebar'
                  ? 'bg-sidebar-fg text-sidebar'
                  : 'bg-fg text-surface'
                : 'opacity-75 hover:opacity-100',
            )}
          >
            {language}
          </button>
        );
      })}
    </div>
  );
}

export function ThemeToggle() {
  const { t } = useTranslation();
  const { theme, toggleTheme } = useTheme();
  const dark = theme === 'dark';
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={dark ? t('preferences.switchToLight') : t('preferences.switchToDark')}
      title={dark ? t('preferences.switchToLight') : t('preferences.switchToDark')}
      className="inline-flex size-8 items-center justify-center rounded-md ring-1 ring-inset ring-current/20 opacity-85 hover:opacity-100"
    >
      {dark ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
    </button>
  );
}
