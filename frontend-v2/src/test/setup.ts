import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest';
import i18n from '@/i18n';
import { server } from './server';

// Lazy routes load on first render; under a parallel full-suite run that can exceed 1s.
configure({ asyncUtilTimeout: 3000 });

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

beforeEach(async () => {
  localStorage.clear();
  sessionStorage.clear();
  document.documentElement.dataset.theme = 'light';
  await i18n.changeLanguage('tr');
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

afterAll(() => server.close());
