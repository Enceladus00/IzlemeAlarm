/**
 * Permission codes seeded by alembic/versions/0002_rbac.py. The API is the
 * authorization boundary; the UI uses these only to hide what would fail.
 */
export const PERMISSIONS = [
  'user:manage',
  'role:manage',
  'upload:create',
  'upload:view',
  'rule:view',
  'rule:edit',
  'customer:view',
  'alert:view',
  'alert:update',
  'dashboard:view',
  'audit:view',
] as const;

export type Permission = (typeof PERMISSIONS)[number];

export type PermissionSet = ReadonlySet<string>;

export function hasPermission(permissions: PermissionSet, permission: Permission): boolean {
  return permissions.has(permission);
}

export function hasAnyPermission(
  permissions: PermissionSet,
  required: readonly Permission[],
): boolean {
  return required.some((permission) => permissions.has(permission));
}
