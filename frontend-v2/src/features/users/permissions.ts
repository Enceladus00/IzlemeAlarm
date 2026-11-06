import type { Role } from '@/api/schemas/users';

/** Display order of the permission catalogue (database/V2, V5). Unknown codes go last. */
const PERMISSION_ORDER = [
  'alert:view',
  'alert:update',
  'alert:escalate',
  'alert:confirm',
  'customer:view',
  'dashboard:view',
  'rule:view',
  'rule:edit',
  'audit:view',
  'upload:view',
  'upload:create',
  'user:manage',
  'role:manage',
];

const rank = (code: string) => {
  const index = PERMISSION_ORDER.indexOf(code);
  return index === -1 ? PERMISSION_ORDER.length : index;
};

/** Every permission held by at least one active role, in catalogue order. */
export function permissionUniverse(roles: Role[]): string[] {
  const all = new Set(roles.flatMap((role) => role.permissions));
  return [...all].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

export function splitPermissions(role: Role, universe: string[]) {
  const held = new Set(role.permissions);
  return {
    can: universe.filter((code) => held.has(code)),
    cannot: universe.filter((code) => !held.has(code)),
  };
}
