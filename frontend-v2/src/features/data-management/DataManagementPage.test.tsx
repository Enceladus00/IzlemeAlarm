import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { renderApp, storeSession } from '@/test/render';
import { API, server } from '@/test/server';
import { CSV_TEMPLATES, rejectionCsv } from './api';

const downloads: { name: string; text: string }[] = [];
vi.mock('@/utils/csv', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/utils/csv')>();
  return { ...original, downloadText: (name: string, text: string) => downloads.push({ name, text }) };
});

const uploadResult = {
  batch_id: 7,
  entity_type: 'customer',
  total_rows: 3,
  accepted_rows: 1,
  rejected_rows: 2,
  errors: [
    { row_number: 3, reason: 'customer_no already exists', row_data: { customer_no: 'C-1', full_name: 'Ayşe, "AK"' } },
    { row_number: 4, reason: 'full_name is required', row_data: { customer_no: 'C-2', full_name: '' } },
  ],
};

let uploads: { entity: string | null; fileName: string | null; content: string }[] = [];
beforeEach(() => {
  uploads = [];
  downloads.length = 0;
  server.use(
    http.post(`${API}/uploads`, async ({ request }) => {
      const form = await request.formData();
      const file = form.get('file') as File | null;
      uploads.push({ entity: new URL(request.url).searchParams.get('entity'), fileName: file?.name ?? null, content: (await file?.text()) ?? '' });
      return HttpResponse.json(uploadResult);
    }),
    http.get(`${API}/uploads/7`, () => HttpResponse.json({ ...uploadResult, file_name: 'customers.csv', uploaded_at: '2026-11-02T09:30:00', own_upload: true })),
    http.get(`${API}/uploads/99`, () => HttpResponse.json({ detail: 'Upload batch not found.' }, { status: 404 })),
  );
});

const csvFile = (name = 'customers.csv', content = CSV_TEMPLATES.customer) => new File([content], name, { type: 'text/csv' });

describe('Data management', () => {
  it('uploads a CSV and shows the row-level rejection report', async () => {
    storeSession('admin');
    const { user } = renderApp('/data');
    await user.upload(await screen.findByLabelText('CSV dosyası'), csvFile());
    expect(screen.getByText(/customers\.csv/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Doğrula ve yükle' }));

    expect(await screen.findByText('1 kabul edildi, 2 reddedildi (3 satır).')).toBeInTheDocument();
    // (jsdom's File loses its name in Node's multipart encoder; browsers send it.)
    expect(uploads).toMatchObject([{ entity: 'customer', content: CSV_TEMPLATES.customer }]);
    const table = screen.getByRole('table', { name: 'Reddedilen satırlar' });
    expect(within(table).getByText('customer_no already exists')).toBeInTheDocument();
    expect(within(table).getByText(/full_name=Ayşe, "AK"/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Ret raporunu indir (CSV)' }));
    expect(downloads).toHaveLength(1);
    expect(downloads[0]!.name).toBe('upload-7-rejections.csv');
    expect(downloads[0]!.text).toContain('row_number,reason,customer_no,full_name');
  });

  it('downloads the template for the chosen entity', async () => {
    storeSession('admin');
    const { user } = renderApp('/data');
    await user.selectOptions(await screen.findByLabelText('Veri türü'), 'transaction');
    expect(screen.getByText(/transaction_no, sender_account_no/)).toBeInTheDocument();
    expect(screen.getByText('İşlem yüklemesi kabul edilen satırlar için kuralları otomatik olarak çalıştırır.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'CSV şablonunu indir' }));
    expect(downloads[0]).toEqual({ name: 'transaction_template.csv', text: CSV_TEMPLATES.transaction });
  });

  it('rejects non-CSV and oversized files before uploading', async () => {
    storeSession('admin');
    const { user } = renderApp('/data', { userEventOptions: { applyAccept: false } });
    const input = await screen.findByLabelText('CSV dosyası');
    await user.upload(input, new File(['x'], 'notes.txt', { type: 'text/plain' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Bir .csv dosyası seçin.');

    const big = new File(['x'], 'big.csv', { type: 'text/csv' });
    Object.defineProperty(big, 'size', { value: 6 * 1024 * 1024 });
    await user.upload(input, big);
    expect(screen.getByRole('alert')).toHaveTextContent('Dosya 5 MB sınırını aşıyor.');
    expect(screen.getByRole('button', { name: 'Doğrula ve yükle' })).toBeDisabled();
    expect(uploads).toHaveLength(0);
  });

  it('shows server-side file errors', async () => {
    server.use(http.post(`${API}/uploads`, () => HttpResponse.json({ detail: 'Missing CSV columns: risk_level' }, { status: 422 })));
    storeSession('admin');
    const { user } = renderApp('/data');
    await user.upload(await screen.findByLabelText('CSV dosyası'), csvFile());
    await user.click(screen.getByRole('button', { name: 'Doğrula ve yükle' }));
    expect(await screen.findByText('Missing CSV columns: risk_level')).toBeInTheDocument();
  });

  it('looks up a previous report, defaulting to the last upload', async () => {
    storeSession('admin');
    const { user } = renderApp('/data');
    await user.upload(await screen.findByLabelText('CSV dosyası'), csvFile());
    await user.click(screen.getByRole('button', { name: 'Doğrula ve yükle' }));
    await screen.findByText('1 kabul edildi, 2 reddedildi (3 satır).');

    expect(screen.getByLabelText('Yükleme numarası')).toHaveValue(7);
    await user.click(screen.getByRole('button', { name: 'Raporu getir' }));
    expect(await screen.findByText('customers.csv')).toBeInTheDocument();
    expect(screen.getByText('02.11.2026 09:30')).toBeInTheDocument();

    await user.clear(screen.getByLabelText('Yükleme numarası'));
    await user.type(screen.getByLabelText('Yükleme numarası'), '99');
    await user.click(screen.getByRole('button', { name: 'Raporu getir' }));
    expect(await screen.findByText('Bu numarada bir yükleme bulunamadı.')).toBeInTheDocument();
  });

  it('offers only reports with upload:view', async () => {
    storeSession('uploadviewer');
    renderApp('/data');
    expect(await screen.findByText('Hesabınız yükleme raporlarını görebilir ancak yeni dosya yükleyemez.')).toBeInTheDocument();
    expect(screen.queryByLabelText('CSV dosyası')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Raporu getir' })).toBeInTheDocument();
  });
});

describe('rejectionCsv', () => {
  it('quotes values and includes every original column', () => {
    expect(rejectionCsv(uploadResult.errors)).toBe(
      'row_number,reason,customer_no,full_name\r\n3,customer_no already exists,C-1,"Ayşe, ""AK"""\r\n4,full_name is required,C-2,\r\n',
    );
  });

  it('lists recent uploads, opens a report from the list and hides other users’ row data (K13)', async () => {
    server.use(
      http.get(`${API}/uploads`, () =>
        HttpResponse.json([
          { batch_id: 12, entity_type: 'customer', file_name: 'b.csv', total_rows: 2, accepted_rows: 1, rejected_rows: 1, uploaded_at: '2026-11-03T09:00:00', uploaded_by_name: 'veri.yukleyici' },
        ]),
      ),
      http.get(`${API}/uploads/12`, () =>
        HttpResponse.json({
          batch_id: 12,
          entity_type: 'customer',
          file_name: 'b.csv',
          total_rows: 2,
          accepted_rows: 1,
          rejected_rows: 1,
          uploaded_at: '2026-11-03T09:00:00',
          own_upload: false,
          errors: [{ row_number: 2, reason: 'monthly_income must be positive', row_data: null }],
        }),
      ),
    );
    storeSession('admin');
    const { user } = renderApp('/data');
    const history = await screen.findByRole('table', { name: 'Yükleme geçmişi' });
    expect(within(history).getByText('veri.yukleyici')).toBeInTheDocument();
    await user.click(within(history).getByRole('button', { name: '#12' }));
    expect(await screen.findByText('monthly_income must be positive')).toBeInTheDocument();
    expect(screen.getByText(/reddedilen satırların içeriği gösterilmez/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Ret raporunu indir|Reddedilen satırları indir/ })).not.toBeInTheDocument();
  });
});
