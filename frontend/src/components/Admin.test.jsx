import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal()),
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import { api } from '../lib/api';
import Admin from './Admin';

const DASHBOARD = {
  organizations: [
    { id: 'o1', name: 'Acme', industry: 'Tech', connector_type: 'internal', user_count: 2 },
    { id: 'o2', name: 'Globex', industry: '', connector_type: 'hubspot', user_count: 0 },
  ],
  users: [
    { id: 'u1', email: 'ann@acme.co', role: 'admin', org_id: 'o1', org_name: 'Acme' },
    { id: 'u2', email: 'bob@acme.co', role: 'user', org_id: 'o1', org_name: 'Acme' },
  ],
};

const admin = { email: 'root@lia.co', role: 'owner' };

async function renderAdmin() {
  const user = userEvent.setup();
  const onLogout = vi.fn();
  render(<Admin user={admin} onLogout={onLogout} />);
  await screen.findByRole('table', { name: 'Recent organizations' });
  return { user, onLogout };
}

const submit = (name) => within(screen.getByRole('main')).getByRole('button', { name });
const openTab = (user, name) => user.click(screen.getByRole('button', { name }));

describe('Admin', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: DASHBOARD });
  });

  it('shows a loading state, then the dashboard with landmarks', async () => {
    render(<Admin user={admin} onLogout={() => {}} />);
    expect(screen.getByText('Loading dashboard...')).toBeInTheDocument();
    expect(await screen.findByRole('table', { name: 'Recent users' })).toBeInTheDocument();
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Admin sections' })).toBeInTheDocument();
    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByText('Total organizations').parentElement).toHaveTextContent('2');
  });

  it('shows an error with a retry when the dashboard fails to load', async () => {
    const user = userEvent.setup();
    api.get.mockRejectedValueOnce({ response: { status: 500, data: { error: 'Internal server error' } } });
    render(<Admin user={admin} onLogout={() => {}} />);
    expect(await screen.findByText(/Internal server error/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('table', { name: 'Recent organizations' })).toBeInTheDocument();
    expect(screen.queryByText(/Internal server error/)).not.toBeInTheDocument();
  });

  it('shows empty states', async () => {
    const user = userEvent.setup();
    api.get.mockResolvedValue({ data: { organizations: [], users: [] } });
    render(<Admin user={admin} onLogout={() => {}} />);
    expect(await screen.findByText(/No organizations yet/)).toBeInTheDocument();
    await openTab(user, 'Manage users');
    expect(screen.getByText('No users found.')).toBeInTheDocument();
    await openTab(user, 'Organizations');
    expect(screen.getByText('No organizations yet.')).toBeInTheDocument();
  });

  it('lists users and filters by organization', async () => {
    const { user } = await renderAdmin();
    await openTab(user, 'Manage users');
    const table = screen.getByRole('table', { name: 'Users' });
    expect(within(table).getByText('ann@acme.co')).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Filter by organization'), 'o2');
    expect(screen.getByText('No users found for the selected organization.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clear filter' }));
    expect(screen.getByText('bob@acme.co')).toBeInTheDocument();
  });

  it('validates the create-user form before calling the API', async () => {
    const { user } = await renderAdmin();
    await openTab(user, 'Create user');

    await user.click(submit('Create user'));
    expect(screen.getByText("Enter the user's email address.")).toBeInTheDocument();
    expect(screen.getByText('Enter a password.')).toBeInTheDocument();
    expect(screen.getByText('Select an organization.')).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toHaveFocus();
    expect(api.post).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText('Email'), 'new@acme.co');
    await user.type(screen.getByLabelText('Password'), '123');
    await user.selectOptions(screen.getByLabelText('Organization'), 'o1');
    await user.click(submit('Create user'));
    expect(screen.getByText('Password must be at least 6 characters.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('creates a user and announces success', async () => {
    const { user } = await renderAdmin();
    api.post.mockResolvedValue({ data: { user: { email: 'new@acme.co' } } });
    await openTab(user, 'Create user');

    await user.type(screen.getByLabelText('Email'), 'new@acme.co');
    await user.type(screen.getByLabelText('Password'), 'secret12');
    await user.selectOptions(screen.getByLabelText('Organization'), 'o1');
    await user.selectOptions(screen.getByLabelText('Role'), 'admin');
    await user.click(submit('Create user'));

    expect(await screen.findByText('User "new@acme.co" created successfully.')).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith('/admin/users', {
      email: 'new@acme.co',
      password: 'secret12',
      org_id: 'o1',
      role: 'admin',
    });
    expect(screen.getByLabelText('Email')).toHaveValue('');
    expect(api.get).toHaveBeenCalledTimes(2); // dashboard reloaded
  });

  it('shows the server error when creating a user fails', async () => {
    const { user } = await renderAdmin();
    api.post.mockRejectedValue({ response: { status: 400, data: { error: 'Email already exists' } } });
    await openTab(user, 'Create user');
    await user.type(screen.getByLabelText('Email'), 'ann@acme.co');
    await user.type(screen.getByLabelText('Password'), 'secret12');
    await user.selectOptions(screen.getByLabelText('Organization'), 'o1');
    await user.click(submit('Create user'));
    expect(await screen.findByText('Email already exists')).toBeInTheDocument();
  });

  it('asks for confirmation before deleting a user, and cancel keeps the user', async () => {
    const { user } = await renderAdmin();
    await openTab(user, 'Manage users');

    const trigger = screen.getByRole('button', { name: 'Delete bob@acme.co' });
    await user.click(trigger);
    const dialog = screen.getByRole('alertdialog', { name: 'Delete user?' });
    expect(dialog).toHaveTextContent('bob@acme.co');
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus();

    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(api.delete).not.toHaveBeenCalled();
    expect(trigger).toHaveFocus();
  });

  it('closes the confirm dialog with Escape', async () => {
    const { user } = await renderAdmin();
    await openTab(user, 'Manage users');
    await user.click(screen.getByRole('button', { name: 'Delete bob@acme.co' }));
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('deletes a user after confirmation', async () => {
    const { user } = await renderAdmin();
    api.delete.mockResolvedValue({ data: {} });
    await openTab(user, 'Manage users');

    await user.click(screen.getByRole('button', { name: 'Delete bob@acme.co' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/admin/users/u2'));
    expect(await screen.findByText('User deleted successfully.')).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('confirms and deletes an organization, warning about its users', async () => {
    const { user } = await renderAdmin();
    api.delete.mockResolvedValue({ data: {} });
    await openTab(user, 'Organizations');

    await user.click(screen.getByRole('button', { name: 'Delete Acme' }));
    const dialog = screen.getByRole('alertdialog', { name: 'Delete organization?' });
    expect(dialog).toHaveTextContent(/all users in this organization/);
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/admin/organizations/o1'));
  });

  it('keeps the dialog closed and shows an error when deletion fails', async () => {
    const { user } = await renderAdmin();
    api.delete.mockRejectedValue({ response: { data: { error: 'Cannot delete' } } });
    await openTab(user, 'Manage users');
    await user.click(screen.getByRole('button', { name: 'Delete bob@acme.co' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('Cannot delete')).toBeInTheDocument();
  });

  it('validates and submits a password reset', async () => {
    const { user } = await renderAdmin();
    api.put.mockResolvedValue({ data: {} });
    await openTab(user, 'Manage users');
    await user.click(screen.getByRole('button', { name: 'Reset password for ann@acme.co' }));

    const dialog = screen.getByRole('dialog', { name: /Reset password for ann@acme.co/ });
    expect(within(dialog).getByLabelText('New password')).toHaveFocus();
    await user.click(within(dialog).getByRole('button', { name: 'Reset password' }));
    expect(within(dialog).getByText('Enter a new password.')).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText('New password'), '12');
    await user.click(within(dialog).getByRole('button', { name: 'Reset password' }));
    expect(within(dialog).getByText(/at least 6/)).toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();

    await user.type(within(dialog).getByLabelText('New password'), '3456');
    await user.click(within(dialog).getByRole('button', { name: 'Reset password' }));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/admin/users/u1/reset-password', { password: '123456' }),
    );
    expect(await screen.findByText('Password reset successfully for ann@acme.co.')).toBeInTheDocument();
  });

  it('traps Tab focus inside the dialog', async () => {
    const { user } = await renderAdmin();
    await openTab(user, 'Manage users');
    await user.click(screen.getByRole('button', { name: 'Reset password for ann@acme.co' }));
    const dialog = screen.getByRole('dialog');
    const input = within(dialog).getByLabelText('New password');
    const cancel = within(dialog).getByRole('button', { name: 'Cancel' });
    cancel.focus();
    await user.tab();
    expect(input).toHaveFocus();
    await user.tab({ shift: true });
    expect(cancel).toHaveFocus();
  });

  it('edits a user', async () => {
    const { user } = await renderAdmin();
    api.put.mockResolvedValue({ data: {} });
    await openTab(user, 'Manage users');
    await user.click(screen.getByRole('button', { name: 'Edit bob@acme.co' }));

    expect(screen.getByRole('button', { name: 'Edit user' })).toHaveAttribute('aria-current', 'page');
    await user.selectOptions(screen.getByLabelText('Role'), 'owner');
    await user.click(screen.getByRole('button', { name: 'Save user' }));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/admin/users/u2', { email: 'bob@acme.co', role: 'owner', org_id: 'o1' }),
    );
    expect(await screen.findByText('User updated successfully.')).toBeInTheDocument();
  });

  it('validates the create-organization form, including connector fields', async () => {
    const { user } = await renderAdmin();
    await openTab(user, 'Create organization');
    await user.click(submit('Create organization'));
    expect(screen.getByText('Enter the organization name.')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Organization name'), 'Initech');
    await user.selectOptions(screen.getByLabelText('Connector type'), 'postgresql');
    await user.click(submit('Create organization'));
    expect(screen.getByText('Host is required.')).toBeInTheDocument();
    expect(screen.getByLabelText('Host')).toHaveFocus();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('creates an organization with an external connector', async () => {
    const { user } = await renderAdmin();
    api.post.mockResolvedValue({ data: { organization: { name: 'Initech' } } });
    await openTab(user, 'Create organization');

    await user.type(screen.getByLabelText('Organization name'), 'Initech');
    await user.selectOptions(screen.getByLabelText('Connector type'), 'hubspot');
    await user.type(screen.getByLabelText('API Key'), 'key-123');
    await user.click(submit('Create organization'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/admin/organizations', {
        name: 'Initech',
        industry: '',
        connector_type: 'hubspot',
        connector_config: { api_key: 'key-123' },
      }),
    );
    expect(await screen.findByText('Organization "Initech" created successfully.')).toBeInTheDocument();
  });

  it('does not send a connector_config when editing an org without touching credentials', async () => {
    const { user } = await renderAdmin();
    api.put.mockResolvedValue({ data: {} });
    await openTab(user, 'Organizations');
    await user.click(screen.getByRole('button', { name: 'Edit Globex' }));

    await user.type(screen.getByLabelText('Industry'), 'Retail');
    await user.click(screen.getByRole('button', { name: 'Save organization' }));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/admin/organizations/o2', {
        name: 'Globex',
        industry: 'Retail',
        connector_type: 'hubspot',
      }),
    );
  });

  it('never sends the secret mask back when editing connector credentials', async () => {
    const { user } = await renderAdmin();
    api.put.mockResolvedValue({ data: {} });
    await openTab(user, 'Organizations');
    await user.click(screen.getByRole('button', { name: 'Edit Globex' }));

    await user.type(screen.getByLabelText('API Key'), '********');
    await user.click(screen.getByRole('button', { name: 'Save organization' }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    expect(api.put.mock.calls[0][1]).not.toHaveProperty('connector_config');
  });

  it('cancels editing and returns to the list', async () => {
    const { user } = await renderAdmin();
    await openTab(user, 'Organizations');
    await user.click(screen.getByRole('button', { name: 'Edit Acme' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('table', { name: 'Organizations' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit organization' })).not.toBeInTheDocument();
  });

  it('logs out', async () => {
    const { user, onLogout } = await renderAdmin();
    await user.click(screen.getByRole('button', { name: 'Log out' }));
    expect(onLogout).toHaveBeenCalled();
  });
});
