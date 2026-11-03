import { ADMIN_PERMISSIONS, ANALYST_PERMISSIONS } from '@/test/server';
import { homePath, isReadOnly, NAV_ITEMS, visibleNavItems } from './navigation';

const ids = (permissions: string[]) => visibleNavItems(new Set(permissions)).map((item) => item.id);

describe('permission-aware navigation (parity with frontend/app.py)', () => {
  it('shows every screen to an administrator', () => {
    expect(ids(ADMIN_PERMISSIONS)).toHaveLength(NAV_ITEMS.length);
  });

  it('limits the seeded analyst role to overview, alerts and the demo lab', () => {
    expect(ids(ANALYST_PERMISSIONS)).toEqual(['detectionOverview', 'alerts', 'demoLab']);
  });

  it('opens data management with either upload permission', () => {
    expect(ids(['upload:view'])).toEqual(['dataManagement']);
    expect(ids(['upload:create'])).toEqual(['dataManagement']);
  });

  it('marks rules read-only without rule:edit', () => {
    const rules = NAV_ITEMS.find((item) => item.id === 'rules')!;
    expect(isReadOnly(rules, new Set(['rule:view']))).toBe(true);
    expect(isReadOnly(rules, new Set(['rule:view', 'rule:edit']))).toBe(false);
  });

  it('lands on the first permitted screen, or nowhere', () => {
    expect(homePath(new Set(ANALYST_PERMISSIONS))).toBe('/overview');
    expect(homePath(new Set(['audit:view']))).toBe('/audit');
    expect(homePath(new Set())).toBeNull();
  });
});
