import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { ruleFixtures } from '@/test/ruleData';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

let puts: Array<{ code: string; body: unknown }> = [];

beforeEach(() => {
  puts = [];
  server.use(
    http.get(`${API}/rules`, () => HttpResponse.json(ruleFixtures)),
    http.put(`${API}/rules/:code`, async ({ request, params }) => {
      const body = await request.json();
      puts.push({ code: String(params.code), body });
      return HttpResponse.json({ rule_code: params.code, is_active: false, weight: '0.450', thresholds: {} });
    }),
  );
});

function ruleList() {
  return screen.getByRole('navigation', { name: 'Kurallar' });
}

describe('Rule management', () => {
  it('lists registered rules in natural order, then legacy rules', async () => {
    storeSession('mehmet.ozturk');
    renderApp('/rules');
    await screen.findByRole('heading', { name: /R01 — Near-limit activity/ });
    const codes = within(ruleList()).getAllByRole('button').map((button) => /^R\d+/.exec(button.textContent!)![0]);
    expect(codes).toEqual(['R01', 'R02', 'R03', 'R06', 'R13', 'R1']);
    expect(within(ruleList()).getByText('Eski kurallar')).toBeInTheDocument();
  });

  it('edits limits and saves the exact payload', async () => {
    storeSession('mehmet.ozturk');
    const { user, router } = renderApp('/rules');
    const list = await screen.findByRole('navigation', { name: 'Kurallar' });
    await user.click(within(list).getByRole('button', { name: /R02/ }));
    expect(router.state.location.search).toBe('?rule=R02');

    await user.type(screen.getByLabelText('Para birimi 2'), 'usd');
    await user.type(screen.getByLabelText('Referans tutar 2'), '1500');
    await user.clear(screen.getByLabelText('Birleşik risk ağırlığı'));
    await user.type(screen.getByLabelText('Birleşik risk ağırlığı'), '0.5');
    expect(screen.getByText('Kaydedilmemiş değişiklikler var.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Kural ayarlarını kaydet' }));
    expect(await screen.findByText('Değişiklik gerekçesi zorunlu.')).toBeInTheDocument();
    expect(puts).toHaveLength(0);
    await user.type(screen.getByLabelText(/Değişiklik gerekçesi/), 'Kurum onayı 2026/14');
    await user.click(screen.getByRole('button', { name: 'Kural ayarlarını kaydet' }));

    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toEqual({
      code: 'R02',
      body: {
        is_active: false,
        weight: 0.5,
        thresholds: {
          BIREYSEL: { status: 'APPROVED', values: { limits: { TRY: 50000, USD: 1500 } } },
          KURUMSAL: { status: 'UNSET', values: {} },
        },
        reason: 'Kurum onayı 2026/14',
      },
    });
  });

  it('shows field errors and does not save invalid settings', async () => {
    storeSession('mehmet.ozturk');
    const { user } = renderApp('/rules?rule=R03');
    await screen.findByRole('heading', { name: /R03/ });
    await user.selectOptions(screen.getByLabelText('Bireysel · Parametre durumu'), 'PROVISIONAL');
    await user.type(screen.getByLabelText(/Skor başlangıç noktası/), '5');
    await user.type(screen.getByLabelText(/Yüksek güven noktası/), '3');
    await user.click(screen.getByRole('button', { name: 'Kural ayarlarını kaydet' }));

    expect(await screen.findByText('Yüksek güven noktası başlangıç noktasından büyük olmalıdır.')).toBeInTheDocument();
    expect(screen.getByText('Kaydetmeden önce en az bir para birimi ve referans tutar ekleyin.')).toBeInTheDocument();
    expect(screen.getByText('Nakit yatırma sayılan en az bir kanal seçin.')).toBeInTheDocument();
    expect(screen.getByText('İşaretli alanları düzeltip yeniden deneyin.')).toBeInTheDocument();
    expect(puts).toHaveLength(0);
  });

  it('blocks activation while every customer type is UNSET', async () => {
    storeSession('mehmet.ozturk');
    const { user } = renderApp('/rules?rule=R03');
    await user.click(await screen.findByLabelText('Kural etkin'));
    await user.click(screen.getByRole('button', { name: 'Kural ayarlarını kaydet' }));
    expect(await screen.findByText('Kuralı etkinleştirmek için en az bir müşteri türünü yapılandırın.')).toBeInTheDocument();
    expect(puts).toHaveLength(0);
  });

  it('surfaces server validation and allows discarding edits', async () => {
    server.use(
      http.put(`${API}/rules/:code`, () =>
        HttpResponse.json({ detail: 'Invalid R13 parameter values: decay_high must exceed decay_low' }, { status: 422 }),
      ),
    );
    storeSession('mehmet.ozturk');
    const { user } = renderApp('/rules?rule=R13');
    await screen.findByRole('heading', { name: /R13/ });
    expect(screen.getByLabelText(/Hariç tutulacak nakit/)).toHaveValue('3, 9');
    await user.clear(screen.getByLabelText(/decay_high/));
    await user.type(screen.getByLabelText(/decay_high/), '0.4');
    await user.type(screen.getByLabelText(/Değişiklik gerekçesi/), 'Deneme');
    await user.click(screen.getByRole('button', { name: 'Kural ayarlarını kaydet' }));
    // K7: Turkish wording first, the server's English text as the technical detail.
    expect(await screen.findByText('Kural parametreleri geçersiz; alanları kontrol edin.')).toBeInTheDocument();
    expect(screen.getByText('Invalid R13 parameter values: decay_high must exceed decay_low')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Değişiklikleri geri al' }));
    expect(screen.getByLabelText(/decay_high/)).toHaveValue(0.9);
  });

  it('is read-only without rule:edit', async () => {
    server.use(http.get(`${API}/auth/me`, () => HttpResponse.json({ username: 'viewer', role_code: 'auditor', permissions: ['rule:view'] })));
    storeSession('mehmet.ozturk');
    renderApp('/rules?rule=R02');
    expect(await screen.findByText('Kural ayarları hesabınız için salt okunur.')).toBeInTheDocument();
    expect(screen.getByLabelText('Para birimi 1')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Kural ayarlarını kaydet' })).not.toBeInTheDocument();
  });

  it('shows legacy rules as read-only stored thresholds', async () => {
    storeSession('mehmet.ozturk');
    renderApp('/rules?rule=R1');
    expect(await screen.findByText(/eski kuralın kayıtlı bir uygulaması yok/)).toBeInTheDocument();
    expect(screen.getByText(/"amount_limit": 10000/)).toBeInTheDocument();
  });

  it('explains the rule in the guide', async () => {
    storeSession('mehmet.ozturk');
    const { user } = renderApp('/rules?rule=R13');
    await user.click(await screen.findByRole('button', { name: 'Bu kural nasıl çalışır, ayarlar ne anlama gelir' }));
    expect(screen.getByText(/Uygulanabilirlik: Düşük/)).toBeInTheDocument();
    expect(screen.getByText('Confirm thresholds with compliance.')).toBeInTheDocument();
    expect(screen.getByText('Score against anchors.')).toBeInTheDocument();
  });
});

describe('Rule management · hit rate and change history (E07)', () => {
  it('flags a rule whose alerts are rarely confirmed', async () => {
    server.use(
      http.get(`${API}/dashboard/rule-performance`, () =>
        HttpResponse.json([
          { rule_code: 'R01', name: 'Near-limit activity', is_active: true, evaluated: 300, alerts: 144, avg_alert_score: '0.71', confirmed: 1, closed: 11, hit_rate: 1 / 12, provisional: false },
          { rule_code: 'R02', name: 'Large single', is_active: true, evaluated: 300, alerts: 20, avg_alert_score: '0.95', confirmed: 6, closed: 4, hit_rate: 0.6, provisional: false },
        ]),
      ),
    );
    storeSession('mehmet.ozturk');
    renderApp('/rules');
    await screen.findByRole('heading', { name: /R01 — Near-limit activity/ });
    // R01 is below 10% with enough decisions; R02 is fine.
    expect(await within(ruleList()).findByText('Gözden geçir')).toBeInTheDocument();
    expect(within(ruleList()).getAllByText('Gözden geçir')).toHaveLength(1);
    expect(screen.getByText('İsabet %10 altında: eşikleri gözden geçirin.')).toBeInTheDocument();
    expect(screen.getByText(/144 alarm · 1 şüpheli onaylandı · 11 kapatıldı/)).toBeInTheDocument();
  });

  it('lists saved changes with old and new values and the reason', async () => {
    let historyCalls = 0;
    server.use(
      http.get(`${API}/rules/R01/history`, () => {
        historyCalls += 1;
        return HttpResponse.json([
          {
            change_id: 9,
            changed_at: '2026-10-30T08:30:00',
            actor_name: 'mehmet.ozturk',
            actor_role: 'compliance',
            reason: 'Kurum onayı 2026/14',
            changes: [
              { field: 'weight', old: '1.000', new: '0.450' },
              { field: 'BIREYSEL.status', old: 'UNSET', new: 'PROVISIONAL' },
              { field: 'BIREYSEL.window_days', old: null, new: 7 },
            ],
          },
        ]);
      }),
    );
    storeSession('ayse.karaca');
    const { user } = renderApp('/rules');
    const toggle = await screen.findByRole('button', { name: 'Değişiklik geçmişi' });
    expect(historyCalls).toBe(0); // loaded only when opened
    await user.click(toggle);
    expect(await screen.findByText('Kurum onayı 2026/14')).toBeInTheDocument();
    expect(screen.getByText('Birleşik risk ağırlığı:')).toBeInTheDocument();
    expect(screen.getByText('0.450')).toBeInTheDocument();
    expect(screen.getByText('Bireysel · durum:')).toBeInTheDocument();
    expect(screen.getByText('GEÇİCİ')).toBeInTheDocument();
    expect(screen.getByText('Bireysel · window_days:')).toBeInTheDocument();
  });
});
