import { zodResolver } from '@hookform/resolvers/zod';
import { ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { Navigate, useLocation } from 'react-router';
import { z } from 'zod';
import { ApiError } from '@/api/client';
import { LanguageSwitcher, ThemeToggle } from '@/app/Preferences';
import { Button } from '@/components/ui/Button';
import { ErrorState } from '@/components/ui/ErrorState';
import { Field } from '@/components/ui/Field';
import { InlineAlert } from '@/components/ui/InlineAlert';
import { Input } from '@/components/ui/Input';
import { useAuth } from './auth-context';

const loginSchema = z.object({
  username: z.string().trim().min(1, 'auth.usernameRequired'),
  password: z.string().min(1, 'auth.passwordRequired'),
});
type LoginValues = z.infer<typeof loginSchema>;
type MessageKey = 'auth.usernameRequired' | 'auth.passwordRequired';

export function LoginPage() {
  const { t } = useTranslation();
  const { status, login, signOutReason } = useAuth();
  const location = useLocation();
  const [submitError, setSubmitError] = useState<unknown>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: { username: '', password: '' } });

  if (status === 'authenticated') {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from && from !== '/login' ? from : '/'} replace />;
  }

  const onSubmit = handleSubmit(async ({ username, password }) => {
    setSubmitError(null);
    try {
      await login(username, password);
    } catch (error) {
      setSubmitError(error);
    }
  });

  const invalidCredentials = submitError instanceof ApiError && submitError.status === 401;
  const fieldError = (key?: string) => (key ? t(key as MessageKey) : undefined);

  return (
    <div className="flex min-h-full flex-col bg-bg">
      <div className="flex justify-end gap-2 p-4 text-fg">
        <LanguageSwitcher tone="surface" />
        <ThemeToggle />
      </div>
      <main className="flex flex-1 items-start justify-center px-4 pt-[8vh] pb-12">
        <div className="w-full max-w-sm">
          <div className="mb-6 flex items-center gap-3">
            <span className="flex size-11 items-center justify-center rounded-lg bg-sidebar text-accent">
              <ShieldCheck className="size-6" aria-hidden />
            </span>
            <div>
              <p className="text-lg font-bold">{t('app.name')}</p>
              <p className="text-xs text-muted">{t('app.tagline')}</p>
            </div>
          </div>
          <div className="rounded-lg border border-border bg-surface p-6 shadow-sm">
            <h1 className="text-xl font-bold">{t('auth.title')}</h1>
            <p className="mt-1 mb-5 text-[13px] text-muted">{t('auth.subtitle')}</p>

            {signOutReason === 'expired' && !submitError && (
              <InlineAlert tone="warning" className="mb-4" live>
                {t('auth.expired')}
              </InlineAlert>
            )}
            {signOutReason === 'signedOut' && !submitError && (
              <InlineAlert tone="info" className="mb-4" live>
                {t('auth.signedOut')}
              </InlineAlert>
            )}
            {invalidCredentials && (
              <InlineAlert tone="danger" className="mb-4" live>
                {t('auth.invalidCredentials')}
              </InlineAlert>
            )}
            {submitError !== null && !invalidCredentials && <ErrorState error={submitError} className="mb-4" />}

            <form onSubmit={onSubmit} noValidate className="space-y-4">
              <Field label={t('auth.username')} error={fieldError(errors.username?.message)}>
                <Input autoComplete="username" autoFocus {...register('username')} />
              </Field>
              <Field label={t('auth.password')} error={fieldError(errors.password?.message)}>
                <Input type="password" autoComplete="current-password" {...register('password')} />
              </Field>
              <Button type="submit" variant="primary" className="w-full" loading={isSubmitting}>
                {isSubmitting ? t('auth.submitting') : t('auth.submit')}
              </Button>
            </form>
          </div>
        </div>
      </main>
    </div>
  );
}
