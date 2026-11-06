import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { User } from '@/api/schemas/users';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

const users: User[] = [
  { user_id: 1, username: 'admin', role_code: 'admin', is_active: true, created_at: '2026-10-01T09:00:00' },
  { user_id: 2, username: 'ayse.karaca', role_code: 'analyst', is_active: true, created_at: '2026-10-02T09:00:00' },
  { user_id: 3, username: 'eski.kullanici', role_code: 'analyst', is_active: false, created_at: null },
];

let posts: unknown[] = [];
let patches: Array<{ id: string; body: unknown }> = [];

beforeEach(() => {
  posts = [];
  patches = [];
  server.use(
    http.get(`${API}/users`, () => HttpResponse.json(users)),
    http.get(`${API}/users/roles`, () =>
      HttpResponse.json([
        { role_code: 'admin', name: 'Admin', permissions: ['audit:view', 'user:manage'] },
        { role_code: 'analyst', name: 'Analist', permissions: ['alert:escalate', 'alert:view'] },
      ]),
    ),
    http.post(`${API}/users`, async ({ request }) => {
      const body = (await request.json()) as { username: string; role_code: string };
      posts.push(body);
      return HttpResponse.json({ user_id: 9, username: body.username, role_code: body.role_code, is_active: true, created_at: '2026-11-03T10:00:00' }, { status: 201 });
    }),
    http.patch(`${API}/users/:id`, async ({ request, params }) => {
      const body = (await request.json()) as { role_code?: string; is_active?: boolean };
      patches.push({ id: String(params.id), body });
      const user = users.find((candidate) => String(candidate.user_id) === params.id)!;
      return HttpResponse.json({ ...user, ...body });
    }),
  );
});

describe('User management', () => {
  it('lists users with role, status and the current user marked', async () => {
    storeSession('admin');
    renderApp('/users');
    const table = await screen.findByRole('table', { name: 'Kullanıcı yönetimi' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(3);
    expect(within(rows[0]!).getByText('(siz)')).toBeInTheDocument();
    expect(within(rows[1]!).getByText('Analist')).toBeInTheDocument();
    expect(within(rows[2]!).getByText('Pasif')).toBeInTheDocument();
  });

  it('shows a card per role with what it can and cannot do (E14)', async () => {
    storeSession('admin');
    const { user } = renderApp('/users');
    const analyst = await screen.findByRole('article', { name: 'Analist' });
    const can = within(analyst).getByRole('region', { name: 'Yapabildikleri' });
    const cannot = within(analyst).getByRole('region', { name: 'Yapamadıkları' });
    expect(within(can).getByText('Yeni alarmı uyum görevlisine yükseltir')).toBeInTheDocument();
    expect(within(cannot).getByText('Kullanıcı oluşturur, rol atar, hesabı kapatır')).toBeInTheDocument();
    const admin = screen.getByRole('article', { name: 'Yönetici' });
    expect(within(within(admin).getByRole('region', { name: 'Yapamadıkları' })).getByText('Alarmları ve alarma bağlı inceleme verilerini görür')).toBeInTheDocument();

    // The create form summarises the selected role and follows the selection.
    await user.click(screen.getByRole('button', { name: 'Kullanıcı oluştur' }));
    const summary = within(screen.getByRole('dialog')).getByTestId('selected-role-permissions');
    expect(within(summary).getByText('Yeni alarmı uyum görevlisine yükseltir')).toBeInTheDocument();
    await user.selectOptions(within(screen.getByRole('dialog')).getByLabelText('Rol'), 'admin');
    expect(within(within(summary).getByRole('region', { name: 'Yapabildikleri' })).getByText('Denetim kaydını görür')).toBeInTheDocument();
  });

  it('validates and creates a user', async () => {
    storeSession('admin');
    const { user } = renderApp('/users');
    await user.click(await screen.findByRole('button', { name: 'Kullanıcı oluştur' }));
    const dialog = screen.getByRole('dialog', { name: 'Yeni kullanıcı' });
    await user.click(within(dialog).getByRole('button', { name: 'Kullanıcı oluştur' }));
    expect(within(dialog).getByText('Kullanıcı adını girin.')).toBeInTheDocument();
    expect(within(dialog).getByText('İlk parolayı girin.')).toBeInTheDocument();

    // 25 × "ş" = 50 UTF-8 bytes; 37 × "ş" = 74 bytes exceeds bcrypt's 72-byte limit.
    await user.type(within(dialog).getByLabelText('İlk parola'), 'ş'.repeat(37));
    await user.click(within(dialog).getByRole('button', { name: 'Kullanıcı oluştur' }));
    expect(within(dialog).getByText('Parola en fazla 72 bayt (UTF-8) olabilir.')).toBeInTheDocument();

    await user.clear(within(dialog).getByLabelText('İlk parola'));
    await user.type(within(dialog).getByLabelText('İlk parola'), 'Güçlü-Parola-1');
    await user.type(within(dialog).getByLabelText('Kullanıcı adı'), '  mehmet.oz  ');
    await user.click(within(dialog).getByRole('button', { name: 'Kullanıcı oluştur' }));

    expect(await screen.findByText('mehmet.oz oluşturuldu.')).toBeInTheDocument();
    expect(posts).toEqual([{ username: 'mehmet.oz', password: 'Güçlü-Parola-1', role_code: 'analyst' }]);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows a duplicate-username conflict from the API', async () => {
    server.use(http.post(`${API}/users`, () => HttpResponse.json({ detail: 'Username already exists.' }, { status: 409 })));
    storeSession('admin');
    const { user } = renderApp('/users');
    await user.click(await screen.findByRole('button', { name: 'Kullanıcı oluştur' }));
    const dialog = screen.getByRole('dialog');
    await user.type(within(dialog).getByLabelText('Kullanıcı adı'), 'admin');
    await user.type(within(dialog).getByLabelText('İlk parola'), 'x');
    await user.click(within(dialog).getByRole('button', { name: 'Kullanıcı oluştur' }));
    expect(await within(dialog).findByText('Username already exists.')).toBeInTheDocument();
    expect(within(dialog).getByText('Bu kullanıcı adı kullanılıyor.')).toBeInTheDocument();
  });

  it('sends only changed fields when editing', async () => {
    storeSession('admin');
    const { user } = renderApp('/users');
    await user.click(await screen.findByRole('button', { name: 'ayse.karaca kullanıcısını düzenle' }));
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Kullanıcıyı kaydet' }));
    expect(within(dialog).getByText('Değişiklik yok.')).toBeInTheDocument();
    expect(patches).toHaveLength(0);

    await user.click(within(dialog).getByLabelText('Hesap etkin'));
    await user.click(within(dialog).getByRole('button', { name: 'Kullanıcıyı kaydet' }));
    await waitFor(() => expect(patches).toEqual([{ id: '2', body: { is_active: false } }]));
    expect(await screen.findByText('ayse.karaca güncellendi.')).toBeInTheDocument();
  });

  it('warns before editing your own account', async () => {
    storeSession('admin');
    const { user } = renderApp('/users');
    await user.click(await screen.findByRole('button', { name: 'admin kullanıcısını düzenle' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/Kendi hesabınızı düzenliyorsunuz/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Rol')).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Kullanıcıyı kaydet' })).toBeDisabled();
  });
});
