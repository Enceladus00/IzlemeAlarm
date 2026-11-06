import { Check, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Role } from '@/api/schemas/users';
import { Card, CardHeader } from '@/components/ui/Card';
import { permissionUniverse, splitPermissions } from './permissions';

function usePermissionLabel() {
  const { t } = useTranslation();
  return (code: string) => {
    const key = `permissions.${code.replace(':', '_')}`;
    // Unknown (newly added) permissions fall back to their code.
    return t(key as 'permissions.alert_view', { defaultValue: code });
  };
}

export function PermissionLists({ role, universe, compact = false }: { role: Role; universe: string[]; compact?: boolean }) {
  const { t } = useTranslation();
  const label = usePermissionLabel();
  const { can, cannot } = splitPermissions(role, universe);
  const list = (codes: string[], allowed: boolean) => (
    <ul className="mt-1.5 space-y-1">
      {codes.length === 0 && <li className="text-muted">{t('users.nothing')}</li>}
      {codes.map((code) => (
        <li key={code} className="flex items-start gap-1.5">
          {allowed ? (
            <Check className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden />
          ) : (
            <X className="mt-0.5 size-3.5 shrink-0 text-muted" aria-hidden />
          )}
          <span className={allowed ? undefined : 'text-muted'}>{label(code)}</span>
        </li>
      ))}
    </ul>
  );
  return (
    <div className={compact ? 'grid gap-3 text-xs sm:grid-cols-2' : 'grid gap-4 text-[13px]'}>
      <section aria-label={t('users.canDo')}>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-success">{t('users.canDo')}</h4>
        {list(can, true)}
      </section>
      <section aria-label={t('users.cannotDo')}>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">{t('users.cannotDo')}</h4>
        {list(cannot, false)}
      </section>
    </div>
  );
}

/** E14 — one card per active role with what it can and cannot do. */
export function RoleCards({ roles, roleName }: { roles: Role[]; roleName: (code: string) => string }) {
  const { t } = useTranslation();
  const universe = permissionUniverse(roles);
  return (
    <Card className="mb-4">
      <CardHeader title={t('users.roleCardsTitle')} description={t('users.roleCardsDescription')} />
      <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-4">
        {roles.map((role) => (
          <article key={role.role_code} aria-label={roleName(role.role_code)} className="rounded-md border border-border p-4">
            <h3 className="mb-3 text-sm font-semibold">{roleName(role.role_code)}</h3>
            <PermissionLists role={role} universe={universe} />
          </article>
        ))}
      </div>
    </Card>
  );
}
