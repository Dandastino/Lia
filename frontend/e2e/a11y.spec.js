import { test, expect } from '@playwright/test';
import { ADMIN, login, mockApi } from './helpers';

// Lightweight accessibility smoke checks (no extra dependency): landmarks,
// accessible names, keyboard operation and visible focus.

test.describe('accessibility smoke checks', () => {
  test('login page: landmarks, labels and keyboard-only sign-in', async ({ page }) => {
    await mockApi(page);
    await page.goto('/');

    await expect(page.getByRole('main')).toHaveCount(1);
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');

    // Every form control has an accessible name.
    for (const input of await page.locator('input, select, textarea').all()) {
      const id = await input.getAttribute('id');
      await expect(page.locator(`label[for="${id}"]`)).toHaveCount(1);
    }

    // Tab order follows the visual order and Enter submits.
    await page.keyboard.press('Tab');
    await expect(page.getByLabel('Email')).toBeFocused();
    await page.keyboard.type('admin@lia.test');
    await page.keyboard.press('Tab');
    await expect(page.getByLabel('Password')).toBeFocused();
    await page.keyboard.type('admin-pass');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: 'Lia administration' })).toBeVisible();
  });

  test('focused controls have a visible focus indicator', async ({ page }) => {
    await mockApi(page);
    await page.goto('/');
    await page.keyboard.press('Tab');
    const outline = await page.getByLabel('Email').evaluate((el) => {
      const style = getComputedStyle(el);
      return { width: parseFloat(style.outlineWidth), style: style.outlineStyle };
    });
    expect(outline.style).not.toBe('none');
    expect(outline.width).toBeGreaterThanOrEqual(2);
  });

  test('error messages are announced through a live region', async ({ page }) => {
    await mockApi(page);
    await page.goto('/');
    await page.getByLabel('Email').fill('user@lia.test');
    await page.getByLabel('Password').fill('nope');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.locator('[role="alert"]')).toContainText('Invalid email or password');
  });

  test('admin: skip link, nav landmark, current tab and keyboard tab switching', async ({ page }) => {
    await mockApi(page);
    await login(page, ADMIN.email, 'admin-pass');
    await expect(page.getByRole('heading', { name: 'Lia administration' })).toBeVisible();

    // Skip link is the first tab stop and moves focus to main content.
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('main')).toBeFocused();

    const nav = page.getByRole('navigation', { name: 'Admin sections' });
    await expect(nav.getByRole('button', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page');

    await nav.getByRole('button', { name: 'Organizations' }).focus();
    await page.keyboard.press('Enter');
    await expect(nav.getByRole('button', { name: 'Organizations' })).toHaveAttribute('aria-current', 'page');
    await expect(page.getByRole('heading', { level: 2, name: 'All organizations' })).toBeVisible();

    // Tables have names and header cells.
    const table = page.getByRole('table', { name: 'Organizations' });
    await expect(table.getByRole('columnheader').first()).toBeVisible();
  });

  test('confirm dialog traps focus and restores it on close', async ({ page }) => {
    const state = await mockApi(page);
    state.users.push({ id: 'u-2', email: 'bob@lia.test', role: 'user', org_id: 'o1', org_name: 'Acme' });
    await login(page, ADMIN.email, 'admin-pass');
    await page.getByRole('button', { name: 'Manage users' }).click();

    const trigger = page.getByRole('button', { name: 'Delete bob@lia.test' });
    await trigger.focus();
    await page.keyboard.press('Enter');

    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toHaveAttribute('aria-modal', 'true');
    // Focus cycles between the two buttons only.
    for (let i = 0; i < 5; i += 1) {
      await page.keyboard.press('Tab');
      const inside = await dialog.evaluate((el) => el.contains(document.activeElement));
      expect(inside).toBe(true);
    }
    await page.keyboard.press('Escape');
    await expect(trigger).toBeFocused();
  });

  test('respects prefers-reduced-motion', async ({ page }) => {
    await mockApi(page);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await login(page, ADMIN.email, 'admin-pass');
    await page.getByRole('button', { name: 'Manage users' }).click();
    const duration = await page.getByRole('button', { name: 'Dashboard' }).evaluate((el) => getComputedStyle(el).transitionDuration);
    expect(parseFloat(duration)).toBeLessThan(0.01);
  });

  test('layout has no horizontal scrolling on a phone viewport', async ({ page }) => {
    await mockApi(page);
    await page.setViewportSize({ width: 375, height: 700 });
    await page.goto('/');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);

    await login(page, ADMIN.email, 'admin-pass');
    await expect(page.getByRole('heading', { name: 'Lia administration' })).toBeVisible();
    const adminOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(adminOverflow).toBeLessThanOrEqual(0);
  });
});
