import * as Dialog from '@radix-ui/react-dialog';
import { LogOut, Menu, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink, Outlet, useLocation } from 'react-router';
import { useAuth } from '@/auth/auth-context';
import { useAlertCount } from '@/features/alerts/api';
import { isComplianceUser } from '@/features/alerts/workflow';
import { cn } from '@/utils/cn';
import { formatNumber } from '@/utils/format';
import { isReadOnly, NAV_SECTIONS, visibleNavItems } from './navigation';
import { LanguageSwitcher, ThemeToggle } from './Preferences';
import { SessionCountdown } from './SessionCountdown';

function initials(username: string): string {
  const parts = username.split(/[\s._-]+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0]![0]! + parts[1]![0]! : username.slice(0, 2);
  return letters.toLocaleUpperCase('tr-TR');
}

function Brand() {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 px-1">
      {/* Logo slot: the product has no logo asset yet. */}
      <span
        className="flex size-11 shrink-0 items-center justify-center rounded border border-dashed border-sidebar-muted text-[9px] tracking-wider text-sidebar-muted"
        aria-hidden
      >
        {t('app.logoPlaceholder')}
      </span>
      <div className="min-w-0">
        <p className="text-base font-bold text-sidebar-fg">{t('app.name')}</p>
        <p className="truncate text-xs text-sidebar-muted">{t('app.tagline')}</p>
      </div>
    </div>
  );
}

/** Open alerts waiting for this user's role, beside the alert queue link. */
function NewAlertsBadge() {
  const { t, i18n } = useTranslation();
  const { permissions } = useAuth();
  const status = isComplianceUser(permissions) ? 'in_review' : 'new';
  const count = useAlertCount(status);
  if (!count.data) return null;
  return (
    <span className="rounded-md bg-accent px-1.5 py-0.5 text-[11px] font-bold text-accent-fg tabular-nums">
      {formatNumber(count.data, i18n.resolvedLanguage ?? 'tr')}
      <span className="sr-only"> {t(`alertStatus.${status}`)}</span>
    </span>
  );
}

function SidebarContent() {
  const { t } = useTranslation();
  const { profile, permissions, logout } = useAuth();
  const items = visibleNavItems(permissions);
  const roleLabels: Record<string, string> = {
    admin: t('roles.admin'),
    analyst: t('roles.analyst'),
    auditor: t('roles.auditor'),
    compliance: t('roles.compliance'),
  };
  const roleLabel = profile ? (roleLabels[profile.role_code] ?? profile.role_code) : undefined;

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto px-4 py-5 text-sidebar-fg">
      <Brand />

      {profile && (
        <div className="flex items-center gap-3 rounded-lg bg-sidebar-elevated px-3 py-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-[#2f3a4f] text-xs font-semibold text-white" aria-hidden>
            {initials(profile.username)}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{profile.username}</p>
            <p className="truncate text-xs text-accent">{roleLabel}</p>
          </div>
        </div>
      )}

      <nav aria-label={t('app.mainNavigation')} className="flex-1 space-y-5">
        {NAV_SECTIONS.map((section) => {
          const sectionItems = items.filter((item) => item.section === section);
          if (sectionItems.length === 0) return null;
          return (
            <div key={section}>
              <p className="mb-2 px-3 text-[11px] font-medium tracking-[0.08em] text-sidebar-muted uppercase">
                {t(`nav.sections.${section}`)}
              </p>
              <ul className="space-y-1">
                {sectionItems.map((item) => {
                  const Icon = item.icon;
                  return (
                    <li key={item.id}>
                      <NavLink
                        to={item.path}
                        className={({ isActive }) =>
                          cn(
                            'flex items-center gap-3 rounded-md border-l-[3px] px-3 py-2 text-sm transition-colors',
                            isActive
                              ? 'border-accent bg-sidebar-elevated font-semibold text-sidebar-fg'
                              : 'border-transparent text-sidebar-fg/85 hover:bg-sidebar-elevated/60',
                          )
                        }
                      >
                        <Icon className="size-4 shrink-0" aria-hidden />
                        <span className="flex-1 truncate">{t(`nav.${item.id}`)}</span>
                        {item.id === 'alerts' && <NewAlertsBadge />}
                        {isReadOnly(item, permissions) && (
                          <span className="text-[10px] text-sidebar-muted">{t('nav.readOnly')}</span>
                        )}
                      </NavLink>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      <div className="space-y-3 border-t border-white/10 pt-4">
        <SessionCountdown />
        <div className="flex items-center justify-between gap-2">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium ring-1 ring-inset ring-white/20 hover:bg-sidebar-elevated"
        >
          <LogOut className="size-4" aria-hidden />
          {t('auth.signOut')}
        </button>
      </div>
    </div>
  );
}

export function AppShell() {
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  // Close the mobile drawer after navigating.
  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <div className="min-h-full lg:pl-64">
      <a
        href="#main"
        className="sr-only z-50 rounded bg-surface px-3 py-2 text-fg focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        {t('app.skipToContent')}
      </a>

      <aside className="fixed inset-y-0 left-0 hidden w-64 bg-sidebar lg:block">
        <SidebarContent />
      </aside>

      <Dialog.Root open={menuOpen} onOpenChange={setMenuOpen}>
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 bg-sidebar px-4 text-sidebar-fg lg:hidden">
          <Dialog.Trigger asChild>
            <button type="button" className="rounded-md p-2 hover:bg-sidebar-elevated" aria-label={t('app.openMenu')}>
              <Menu className="size-5" aria-hidden />
            </button>
          </Dialog.Trigger>
          <p className="font-bold">{t('app.name')}</p>
        </header>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 lg:hidden" />
          <Dialog.Content
            className="fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] bg-sidebar shadow-xl lg:hidden"
            aria-describedby={undefined}
          >
            <Dialog.Title className="sr-only">{t('app.mainNavigation')}</Dialog.Title>
            <Dialog.Close asChild>
              <button
                type="button"
                className="absolute top-4 right-3 rounded-md p-2 text-sidebar-fg hover:bg-sidebar-elevated"
                aria-label={t('app.closeMenu')}
              >
                <X className="size-5" aria-hidden />
              </button>
            </Dialog.Close>
            <SidebarContent />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1400px] px-4 py-6 outline-none sm:px-6 lg:px-8 lg:py-8">
        <Outlet />
      </main>
    </div>
  );
}
