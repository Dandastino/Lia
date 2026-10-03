import { test, expect } from '@playwright/test';
import { ADMIN, REGULAR, login, mockApi } from './helpers';

test.describe('authentication', () => {
  test('regular user signs in, lands on the assistant and logs out', async ({ page }) => {
    await mockApi(page);
    await login(page, REGULAR.email, 'user-pass');

    await expect(page.getByRole('heading', { level: 1, name: /Lia - Your Personal AI Assistant/ })).toBeVisible();
    await expect(page.getByRole('alert')).toContainText('Voice service is unavailable');
    expect(await page.evaluate(() => localStorage.getItem('token'))).toBe('token-user');

    await page.getByRole('button', { name: 'Log out' }).click();
    await expect(page.getByRole('heading', { name: 'Lia Assistant' })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull();
  });

  test('admin signs in and lands on the administration dashboard', async ({ page }) => {
    await mockApi(page);
    await login(page, ADMIN.email, 'admin-pass');

    await expect(page.getByRole('heading', { level: 1, name: 'Lia administration' })).toBeVisible();
    await expect(page.getByRole('table', { name: 'Recent organizations' })).toContainText('Acme');
    await expect(page).toHaveTitle('Administration - Lia');
  });

  test('wrong credentials show an error and keep the user on the login screen', async ({ page }) => {
    await mockApi(page);
    await login(page, REGULAR.email, 'wrong-password');

    await expect(page.getByRole('alert')).toContainText('Invalid email or password');
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeEnabled();
    expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull();
  });

  test('empty and malformed input is validated before any request', async ({ page }) => {
    const state = await mockApi(page);
    await page.goto('/');

    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByText('Enter your email address.')).toBeVisible();
    await expect(page.getByText('Enter your password.')).toBeVisible();
    await expect(page.getByLabel('Email')).toBeFocused();

    await page.getByLabel('Email').fill('not-an-email');
    await page.getByLabel('Password').fill('x');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByText(/enter a valid email address/i)).toBeVisible();
    expect(state.requests).toHaveLength(0);
  });

  test('a saved session survives a reload, a corrupted one does not break the app', async ({ page }) => {
    await mockApi(page);
    await login(page, ADMIN.email, 'admin-pass');
    await expect(page.getByRole('heading', { name: 'Lia administration' })).toBeVisible();

    await page.reload();
    await expect(page.getByRole('heading', { name: 'Lia administration' })).toBeVisible();

    await page.evaluate(() => localStorage.setItem('user', '{broken json'));
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Lia Assistant' })).toBeVisible();
  });

  test('an expired session (401) sends the admin back to the login screen', async ({ page }) => {
    await mockApi(page, { sessionExpired: true });
    await page.addInitScript(() => {
      localStorage.setItem('token', 'stale');
      localStorage.setItem('user', JSON.stringify({ id: 'x', email: 'admin@lia.test', role: 'owner', org_id: 'o1' }));
    });
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Lia Assistant' })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('token'))).toBeNull();
  });
});
