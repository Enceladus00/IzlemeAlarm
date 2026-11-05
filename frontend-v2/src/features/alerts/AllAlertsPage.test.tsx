import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { makeAlert } from '@/test/alertData';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';

const requests: URLSearchParams[] = [];
const closed = makeAlert({ alert_id: 6100, customer_no: 'C-2001', customer_name: 'Ece Tunç', rule_code: 'R02', status: 'closed' });

beforeEach(() => {
  requests.length = 0;
  server.use(
    http.get(`${API}/alerts`, ({ request }) => {
      const params = new URL(request.url).searchParams;
      requests.push(params);
      return HttpResponse.json({
        total: 31,
        items: [closed],
        counts_by_status: { new: 12, in_review: 4, closed: 31, confirmed_suspicious: 3 },
      });
    }),
    http.get(`${API}/alerts/rule-codes`, () => HttpResponse.json(['R01', 'R02'])),
  );
});

describe('All alerts (E11)', () => {
  it('shows status counts whose parts add up to the total, and pages by 25', async () => {
    storeSession('mehmet.ozturk');
    const { user, router } = renderApp('/all-alerts');
    const statuses = await screen.findByRole('group', { name: 'Durum' });
    await waitFor(() => expect(within(statuses).getByRole('button', { name: /Tümü 50/ })).toBeInTheDocument());
    expect(within(statuses).getByRole('button', { name: /Kapatıldı 31/ })).toBeInTheDocument();
    expect(requests[0]!.get('include_counts')).toBe('true');
    expect(requests[0]!.get('limit')).toBe('25');
    expect(requests[0]!.has('status')).toBe(false);

    await user.click(within(statuses).getByRole('button', { name: /Kapatıldı/ }));
    await waitFor(() => expect(requests.at(-1)!.get('status')).toBe('closed'));
    expect(router.state.location.search).toBe('?status=closed');

    expect(screen.getByRole('link', { name: '#6100' })).toHaveAttribute('href', '/alerts/6100');
    await user.click(screen.getByRole('button', { name: /Sonraki/ }));
    await waitFor(() => expect(requests.at(-1)!.get('offset')).toBe('25'));
  });

  it('is a compliance screen: analysts do not get it in the menu', async () => {
    storeSession('ayse.karaca');
    renderApp('/alerts');
    await screen.findByRole('navigation', { name: /./ });
    expect(screen.queryByRole('link', { name: /Tüm alarmlar/ })).not.toBeInTheDocument();
  });
});
