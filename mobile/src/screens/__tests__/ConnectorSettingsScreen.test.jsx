import { act, fireEvent, render, screen } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import ConnectorSettingsScreen from '../ConnectorSettingsScreen';
import { api } from '../../lib/api';

jest.mock('../../lib/api', () => ({
  ...jest.requireActual('../../lib/api'),
  api: { get: jest.fn(), patch: jest.fn() },
}));

const flush = () => act(async () => {});
const input = (label) => screen.getByLabelText(new RegExp(`^${label}`));
const save = () => fireEvent.press(screen.getByRole('button', { name: 'Save settings' }));

async function setup({ user = { org_id: 'org1' }, org } = {}) {
  if (user) await AsyncStorage.setItem('user', JSON.stringify(user));
  if (org) api.get.mockResolvedValue({ data: { organization: org } });
  else api.get.mockRejectedValue(new Error('no org'));
  const navigation = { goBack: jest.fn() };
  render(<ConnectorSettingsScreen navigation={navigation} />);
  await flush();
  return navigation;
}

describe('ConnectorSettingsScreen', () => {
  beforeEach(() => jest.clearAllMocks());

  it('goes back from an accessible back button', async () => {
    const navigation = await setup();
    fireEvent.press(screen.getByRole('button', { name: 'Back' }));
    expect(navigation.goBack).toHaveBeenCalled();
  });

  it('starts from the template when nothing is stored', async () => {
    await setup();
    expect(input('Host').props.value).toBe('db.example.com');
    expect(input('Password').props.secureTextEntry).toBe(true);
    expect(input('Port').props.keyboardType).toBe('numeric');
  });

  it('loads the stored connector and never sends masked secrets back', async () => {
    await setup({
      org: {
        connector_type: 'mysql',
        connector_config: { host: 'db1', port: 3306, database: 'crm', user: 'lia', password: '********' },
      },
    });
    expect(api.get).toHaveBeenCalledWith('/organizations/org1');
    expect(input('Host').props.value).toBe('db1');
    expect(input('Password').props.value).toBe('********');

    fireEvent.changeText(input('Host'), 'db2');
    api.patch.mockResolvedValue({ status: 200 });
    save();
    await flush();

    expect(api.patch).toHaveBeenCalledWith('/organizations/org1/connector', {
      connector_type: 'mysql',
      connector_config: { host: 'db2', port: 3306, database: 'crm', user: 'lia' },
    });
    expect(screen.getByText('Settings saved successfully.')).toBeOnTheScreen();
  });

  it('sends a newly typed secret', async () => {
    await setup({ org: { connector_type: 'hubspot', connector_config: { api_key: '********' } } });
    fireEvent.changeText(input('API Key'), 'pat-123');
    api.patch.mockResolvedValue({ status: 200 });
    save();
    await flush();
    expect(api.patch.mock.calls[0][1]).toEqual({ connector_type: 'hubspot', connector_config: { api_key: 'pat-123' } });
  });

  it('strips masked values after switching connector type too', async () => {
    await setup();
    fireEvent.press(screen.getByRole('radio', { name: 'HubSpot' }));
    fireEvent.changeText(input('API Key'), '********');
    api.patch.mockResolvedValue({ status: 200 });
    save();
    await flush();
    expect(api.patch.mock.calls[0][1].connector_config).toEqual({});
  });

  it('ignores a stored connector type it cannot edit', async () => {
    await setup({ org: { connector_type: 'internal', connector_config: { a: 'b' } } });
    expect(input('Host').props.value).toBe('db.example.com');
  });

  it('shows the backend error as an alert', async () => {
    await setup();
    api.patch.mockRejectedValue({ response: { data: { error: 'Forbidden' } } });
    save();
    expect(await screen.findByText('Forbidden')).toBeOnTheScreen();
    expect(screen.getByRole('alert')).toBeOnTheScreen();
    expect(screen.queryByText('Settings saved successfully.')).toBeNull();
  });

  it('refuses to save without an organization', async () => {
    await setup({ user: { id: '1' } });
    save();
    await flush();
    expect(screen.getByText('No organization associated with your account.')).toBeOnTheScreen();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it('tolerates a missing stored user', async () => {
    await setup({ user: null });
    save();
    await flush();
    expect(screen.getByText('No organization associated with your account.')).toBeOnTheScreen();
  });

  it('disables saving while the request is running', async () => {
    await setup();
    let resolve;
    api.patch.mockImplementation(() => new Promise((r) => { resolve = r; }));
    save();
    await flush();
    expect(screen.getByRole('button', { name: 'Save settings' }).props.accessibilityState).toMatchObject({
      disabled: true,
      busy: true,
    });
    await act(async () => resolve({ status: 200 }));
  });

  it('clears the success message when a field changes', async () => {
    await setup();
    api.patch.mockResolvedValue({ status: 200 });
    save();
    await flush();
    expect(screen.getByText('Settings saved successfully.')).toBeOnTheScreen();
    fireEvent.changeText(input('Host'), 'other');
    expect(screen.queryByText('Settings saved successfully.')).toBeNull();
  });

  it('moves focus through the fields and submits from the last one', async () => {
    await setup();
    api.patch.mockResolvedValue({ status: 200 });
    expect(input('Host').props.returnKeyType).toBe('next');
    expect(input('Password').props.returnKeyType).toBe('done');
    fireEvent(input('Host'), 'submitEditing');
    fireEvent(input('Password'), 'submitEditing');
    await flush();
    expect(api.patch).toHaveBeenCalledTimes(1);
  });
});
