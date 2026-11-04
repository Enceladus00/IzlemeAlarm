import { zodResolver } from '@hookform/resolvers/zod';
import { Eye, EyeOff, Pencil, UserPlus, Users } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { PASSWORD_MAX_BYTES, USERNAME_MAX, type Role, type User } from '@/api/schemas/users';
import { useAuth } from '@/auth/auth-context';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { DataTable } from '@/components/ui/DataTable';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Field } from '@/components/ui/Field';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { PageHeader } from '@/components/ui/PageHeader';
import { Select } from '@/components/ui/Select';
import { PageSpinner } from '@/components/ui/Spinner';
import { formatDateTime } from '@/utils/format';
import { useCreateUser, useRoles, useUpdateUser, useUsers } from './api';

const utf8Length = (value: string) => new TextEncoder().encode(value).length;

/** Mirrors api_schemas.UserCreate and security.hash_password limits. */
const createSchema = z.object({
  username: z.string().trim().min(1, 'usernameRequired').max(USERNAME_MAX, 'usernameTooLong'),
  password: z
    .string()
    .min(1, 'passwordRequired')
    .refine((value) => utf8Length(value) <= PASSWORD_MAX_BYTES, 'passwordTooLong'),
  role_code: z.string().min(1),
});
type CreateValues = z.infer<typeof createSchema>;

export default function UsersPage() {
  const { t, i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? 'tr';
  const { profile } = useAuth();
  const users = useUsers();
  const roles = useRoles();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const roleName = (code: string) => {
    const known = {
      admin: t('roles.admin'),
      analyst: t('roles.analyst'),
      auditor: t('roles.auditor'),
      compliance: t('roles.compliance'),
    } as Record<string, string>;
    return known[code] ?? roles.data?.find((role) => role.role_code === code)?.name ?? code;
  };

  const header = (
    <PageHeader
      breadcrumb={t('users.breadcrumb')}
      title={t('nav.users')}
      description={t('users.description')}
      actions={
        <Button variant="primary" onClick={() => setCreating(true)} disabled={!roles.data}>
          <UserPlus className="size-4" aria-hidden />
          {t('users.create')}
        </Button>
      }
    />
  );

  if (users.isPending) return <PageSpinner label={t('common.loading')} />;
  if (users.isError || roles.isError) {
    return (
      <>
        {header}
        <ErrorState error={users.error ?? roles.error} onRetry={() => void (users.isError ? users.refetch() : roles.refetch())} />
      </>
    );
  }

  return (
    <>
      {header}
      {notice && (
        <InlineAlert tone="success" className="mb-4" live>
          {notice}
        </InlineAlert>
      )}
      <Card>
        {users.data.length === 0 ? (
          <EmptyState icon={Users} title={t('users.empty')} />
        ) : (
          <>
            <p className="px-5 pt-4 text-xs text-muted">{t('users.count', { count: users.data.length })}</p>
            <div className="px-2 pt-2 pb-3">
              <DataTable
                label={t('nav.users')}
                rows={users.data}
                rowKey={(user) => String(user.user_id)}
                minWidth={560}
                columns={[
                  {
                    key: 'username',
                    header: t('users.username'),
                    render: (user) => (
                      <span className="font-semibold">
                        {user.username}
                        {user.username === profile?.username && <span className="ml-1.5 text-xs font-normal text-muted">({t('users.you')})</span>}
                      </span>
                    ),
                  },
                  { key: 'role', header: t('users.role'), render: (user) => roleName(user.role_code) },
                  {
                    key: 'status',
                    header: t('users.status'),
                    render: (user) => (
                      <Badge tone={user.is_active ? 'success' : 'neutral'} dot>
                        {user.is_active ? t('users.activeBadge') : t('users.inactiveBadge')}
                      </Badge>
                    ),
                  },
                  { key: 'created', header: t('users.created'), render: (user) => <span className="text-muted">{formatDateTime(user.created_at, language)}</span> },
                  {
                    key: 'actions',
                    header: <span className="sr-only">{t('users.edit')}</span>,
                    align: 'right',
                    render: (user) => (
                      <Button size="sm" variant="ghost" onClick={() => setEditing(user)} aria-label={t('users.editTitle', { username: user.username })}>
                        <Pencil className="size-3.5" aria-hidden />
                        {t('users.edit')}
                      </Button>
                    ),
                  },
                ]}
              />
            </div>
          </>
        )}
      </Card>

      {roles.data && (
        <>
          <CreateUserDialog
            open={creating}
            onOpenChange={setCreating}
            roles={roles.data}
            roleName={roleName}
            onCreated={(username) => {
              setCreating(false);
              setNotice(t('users.createdDone', { username }));
            }}
          />
          {editing && (
            <EditUserDialog
              key={editing.user_id}
              user={editing}
              roles={roles.data}
              roleName={roleName}
              isSelf={editing.username === profile?.username}
              onClose={() => setEditing(null)}
              onSaved={(username) => {
                setEditing(null);
                setNotice(t('users.updatedDone', { username }));
              }}
            />
          )}
        </>
      )}
    </>
  );
}

function CreateUserDialog({
  open,
  onOpenChange,
  roles,
  roleName,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  roles: Role[];
  roleName: (code: string) => string;
  onCreated: (username: string) => void;
}) {
  const { t } = useTranslation();
  const create = useCreateUser();
  const [showPassword, setShowPassword] = useState(false);
  const defaultRole = roles.find((role) => role.role_code === 'analyst')?.role_code ?? roles[0]?.role_code ?? '';
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateValues>({ resolver: zodResolver(createSchema), defaultValues: { username: '', password: '', role_code: defaultRole } });

  const close = (next: boolean) => {
    if (!next) {
      reset({ username: '', password: '', role_code: defaultRole });
      create.reset();
      setShowPassword(false);
    }
    onOpenChange(next);
  };

  const message = (key?: string) => (key ? t(`users.${key as 'usernameRequired'}`, { max: key === 'usernameTooLong' ? USERNAME_MAX : PASSWORD_MAX_BYTES }) : undefined);

  return (
    <Modal open={open} onOpenChange={close} title={t('users.createTitle')}>
      <form
        noValidate
        className="space-y-4"
        onSubmit={handleSubmit((values) =>
          create.mutate(
            { username: values.username.trim(), password: values.password, role_code: values.role_code },
            {
              onSuccess: (user) => {
                close(false);
                onCreated(user.username);
              },
            },
          ),
        )}
      >
        <Field label={t('users.username')} error={message(errors.username?.message)}>
          <Input autoComplete="off" maxLength={USERNAME_MAX + 10} {...register('username')} />
        </Field>
        <div className="flex flex-col gap-1.5">
          <Field label={t('users.password')} hint={t('users.passwordHint')} error={message(errors.password?.message)}>
            <Input type={showPassword ? 'text' : 'password'} autoComplete="new-password" {...register('password')} />
          </Field>
          <Button size="sm" variant="ghost" className="self-start" aria-pressed={showPassword} onClick={() => setShowPassword((value) => !value)}>
            {showPassword ? <EyeOff className="size-3.5" aria-hidden /> : <Eye className="size-3.5" aria-hidden />}
            {showPassword ? t('users.hidePassword') : t('users.showPassword')}
          </Button>
        </div>
        <Field label={t('users.role')}>
          <Select {...register('role_code')}>
            {roles.map((role) => (
              <option key={role.role_code} value={role.role_code}>
                {roleName(role.role_code)}
              </option>
            ))}
          </Select>
        </Field>
        {create.isError && <ErrorState error={create.error} title={t('errors.validation')} />}
        <div className="flex justify-end gap-2">
          <Button onClick={() => close(false)}>{t('users.cancel')}</Button>
          <Button type="submit" variant="primary" loading={create.isPending}>
            {t('users.create')}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function EditUserDialog({
  user,
  roles,
  roleName,
  isSelf,
  onClose,
  onSaved,
}: {
  user: User;
  roles: Role[];
  roleName: (code: string) => string;
  isSelf: boolean;
  onClose: () => void;
  onSaved: (username: string) => void;
}) {
  const { t } = useTranslation();
  const update = useUpdateUser();
  const [roleCode, setRoleCode] = useState(user.role_code);
  const [active, setActive] = useState(user.is_active);
  const [unchanged, setUnchanged] = useState(false);
  // A user may hold a role that is no longer active; keep it selectable.
  const options = roles.some((role) => role.role_code === user.role_code) ? roles : [{ role_code: user.role_code, name: user.role_code }, ...roles];

  const save = () => {
    const body: { role_code?: string; is_active?: boolean } = {};
    if (roleCode !== user.role_code) body.role_code = roleCode;
    if (active !== user.is_active) body.is_active = active;
    if (Object.keys(body).length === 0) {
      setUnchanged(true);
      return;
    }
    update.mutate({ userId: user.user_id, body }, { onSuccess: (saved) => onSaved(saved.username) });
  };

  return (
    <Modal open onOpenChange={(open) => !open && onClose()} title={t('users.editTitle', { username: user.username })}>
      <div className="space-y-4">
        {isSelf && <InlineAlert tone="warning">{t('users.selfWarning')}</InlineAlert>}
        <Field label={t('users.role')}>
          <Select
            value={roleCode}
            disabled={isSelf}
            onChange={(event) => {
              setRoleCode(event.target.value);
              setUnchanged(false);
            }}
          >
            {options.map((role) => (
              <option key={role.role_code} value={role.role_code}>
                {roleName(role.role_code)}
              </option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-3 rounded-md border border-border-strong px-3 py-2.5 text-[13px] font-medium">
          <input
            type="checkbox"
            className="size-4 accent-[var(--accent)]"
            checked={active}
            disabled={isSelf}
            onChange={(event) => {
              setActive(event.target.checked);
              setUnchanged(false);
            }}
          />
          {t('users.active')}
        </label>
        {unchanged && <InlineAlert tone="info">{t('users.noChanges')}</InlineAlert>}
        {update.isError && <ErrorState error={update.error} title={t('errors.validation')} />}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>{t('users.cancel')}</Button>
          <Button variant="primary" loading={update.isPending} disabled={isSelf} onClick={save}>
            {t('users.save')}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
