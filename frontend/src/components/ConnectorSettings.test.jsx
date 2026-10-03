import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal()),
  api: { get: vi.fn(), patch: vi.fn() },
}));

import { api } from '../lib/api';
import ConnectorSettings from './ConnectorSettings';

const user = { org_id: 'org-1', role: 'admin' };

describe('ConnectorSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: { organization: { connector_type: 'postgresql', connector_config: {} } } });
  });

  it('renders labelled controls and the template', async () => {
    render(<ConnectorSettings user={user} onBack={() => {}} />);
    expect(await screen.findByLabelText('Connector type')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText('Connector configuration (JSON)')).toBeEnabled());
    expect(screen.getByLabelText('Connector configuration (JSON)').value).toContain('"host"');
    expect(screen.getByRole('main')).toBeInTheDocument();
  });

  it('loads the stored connector with masked secrets', async () => {
    api.get.mockResolvedValue({
      data: { organization: { connector_type: 'mysql', connector_config: { host: 'h', password: '********' } } },
    });
    render(<ConnectorSettings user={user} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByLabelText('Connector type')).toHaveValue('mysql'));
    expect(screen.getByLabelText('Connector configuration (JSON)').value).toContain('********');
    expect(api.get).toHaveBeenCalledWith('/organizations/org-1');
  });

  it('omits unchanged masked secrets when saving', async () => {
    const u = userEvent.setup();
    api.get.mockResolvedValue({
      data: { organization: { connector_type: 'mysql', connector_config: { host: 'h', password: '********' } } },
    });
    api.patch.mockResolvedValue({ status: 200, data: {} });
    render(<ConnectorSettings user={user} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByLabelText('Connector type')).toHaveValue('mysql'));

    await u.click(screen.getByRole('button', { name: 'Save settings' }));
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith('/organizations/org-1/connector', {
        connector_type: 'mysql',
        connector_config: { host: 'h' },
      }),
    );
    expect(await screen.findByText('Settings saved.')).toBeInTheDocument();
  });

  it('switching the type loads that type template', async () => {
    const u = userEvent.setup();
    render(<ConnectorSettings user={user} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByLabelText('Connector configuration (JSON)')).toBeEnabled());
    await u.selectOptions(screen.getByLabelText('Connector type'), 'hubspot');
    expect(screen.getByLabelText('Connector configuration (JSON)').value).toContain('api_key');
  });

  it('rejects invalid JSON with an inline error and focus', async () => {
    const u = userEvent.setup();
    render(<ConnectorSettings user={user} onBack={() => {}} />);
    const area = screen.getByLabelText('Connector configuration (JSON)');
    await waitFor(() => expect(area).toBeEnabled());
    await u.clear(area);
    await u.type(area, '{{broken');
    await u.click(screen.getByRole('button', { name: 'Save settings' }));

    expect(screen.getByText(/must be a valid JSON object/i)).toBeInTheDocument();
    expect(area).toHaveAttribute('aria-invalid', 'true');
    expect(area).toHaveFocus();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it('rejects JSON arrays', async () => {
    const u = userEvent.setup();
    render(<ConnectorSettings user={user} onBack={() => {}} />);
    const area = screen.getByLabelText('Connector configuration (JSON)');
    await waitFor(() => expect(area).toBeEnabled());
    await u.clear(area);
    await u.type(area, '[[1]');
    await u.click(screen.getByRole('button', { name: 'Save settings' }));
    expect(screen.getByText(/must be a valid JSON object/i)).toBeInTheDocument();
  });

  it('shows the server error when saving fails', async () => {
    const u = userEvent.setup();
    api.patch.mockRejectedValue({ response: { status: 403, data: { error: 'Insufficient permissions' } } });
    render(<ConnectorSettings user={user} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByLabelText('Connector configuration (JSON)')).toBeEnabled());
    await u.click(screen.getByRole('button', { name: 'Save settings' }));
    expect(await screen.findByText('Insufficient permissions')).toBeInTheDocument();
    expect(screen.queryByText('Settings saved.')).not.toBeInTheDocument();
  });

  it('still works when loading the current connector fails', async () => {
    api.get.mockRejectedValue({ response: { status: 500 } });
    render(<ConnectorSettings user={user} onBack={() => {}} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save settings' })).toBeEnabled());
  });

  it('goes back', async () => {
    const u = userEvent.setup();
    const onBack = vi.fn();
    render(<ConnectorSettings user={user} onBack={onBack} />);
    await u.click(screen.getByRole('button', { name: /back to assistant/i }));
    expect(onBack).toHaveBeenCalled();
  });
});
