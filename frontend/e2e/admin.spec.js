import { test, expect } from '@playwright/test';
import { ADMIN, login, mockApi } from './helpers';

test.describe('admin panel', () => {
  test('admin creates a user and sees it in the user list', async ({ page }) => {
    const state = await mockApi(page);
    await login(page, ADMIN.email, 'admin-pass');
    await page.getByRole('navigation', { name: 'Admin sections' }).getByRole('button', { name: 'Create user' }).click();

    const main = page.getByRole('main');
    // Validation first: nothing is sent while the form is invalid.
    await main.getByRole('button', { name: 'Create user' }).click();
    await expect(page.getByText('Select an organization.')).toBeVisible();
    expect(state.requests.filter((r) => r.path === '/admin/users')).toHaveLength(0);

    await page.getByLabel('Email').fill('new.hire@lia.test');
    await page.getByLabel('Password').fill('s3cret-pass');
    await page.getByLabel('Organization').selectOption('o1');
    await main.getByRole('button', { name: 'Create user' }).click();

    await expect(page.getByRole('status')).toContainText('User "new.hire@lia.test" created successfully.');
    expect(state.requests.find((r) => r.path === '/admin/users').body).toEqual({
      email: 'new.hire@lia.test',
      password: 's3cret-pass',
      org_id: 'o1',
      role: 'user',
    });

    await page.getByRole('navigation', { name: 'Admin sections' }).getByRole('button', { name: 'Manage users' }).click();
    await expect(page.getByRole('table', { name: 'Users' })).toContainText('new.hire@lia.test');
  });

  test('deleting a user needs confirmation and can be cancelled with Escape', async ({ page }) => {
    const state = await mockApi(page);
    state.users.push({ id: 'u-2', email: 'bob@lia.test', role: 'user', org_id: 'o1', org_name: 'Acme' });
    await login(page, ADMIN.email, 'admin-pass');
    await page.getByRole('button', { name: 'Manage users' }).click();

    const trigger = page.getByRole('button', { name: 'Delete bob@lia.test' });
    await trigger.click();
    const dialog = page.getByRole('alertdialog', { name: 'Delete user?' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused();

    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
    expect(state.requests.some((r) => r.method === 'DELETE')).toBe(false);

    await trigger.click();
    await dialog.getByRole('button', { name: 'Delete' }).click();
    await expect(page.getByRole('status')).toContainText('User deleted successfully.');
    expect(state.requests.some((r) => r.method === 'DELETE' && r.path === '/admin/users/u-2')).toBe(true);
    await expect(page.getByRole('table', { name: 'Users' })).not.toContainText('bob@lia.test');
  });

  test('admin logs out from the header', async ({ page }) => {
    await mockApi(page);
    await login(page, ADMIN.email, 'admin-pass');
    await page.getByRole('button', { name: 'Log out' }).click();
    await expect(page.getByRole('heading', { name: 'Lia Assistant' })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('user'))).toBeNull();
  });
});
