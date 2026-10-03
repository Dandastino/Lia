import { Alert, FlatList } from 'react-native';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import AdminScreen from '../AdminScreen';
import { api } from '../../lib/api';

jest.mock('../../lib/api', () => ({
  ...jest.requireActual('../../lib/api'),
  api: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

const ORGS = [{ id: 'o1', name: 'Acme', industry: 'Tech', connector_type: 'postgresql' }];
const USERS = [{ id: 'u1', email: 'bob@acme.com', role: 'user', org_id: 'o1' }];

const flush = () => act(async () => {});

async function setup({ orgs = ORGS, users = USERS } = {}) {
  api.get.mockResolvedValue({ data: { organizations: orgs, users } });
  const navigation = { replace: jest.fn() };
  render(<AdminScreen navigation={navigation} />);
  await flush();
  return navigation;
}

const openTab = (name) => fireEvent.press(screen.getByRole('tab', { name }));
const press = (name) => fireEvent.press(screen.getByRole('button', { name }));
const input = (label) => screen.getByLabelText(new RegExp(`^${label}`));

describe('AdminScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });

  afterEach(() => jest.restoreAllMocks());

  describe('dashboard', () => {
    it('loads and shows the totals', async () => {
      await setup();
      expect(api.get).toHaveBeenCalledWith('/admin/dashboard');
      expect(screen.getByLabelText('1 organizations')).toBeOnTheScreen();
      expect(screen.getByLabelText('1 users')).toBeOnTheScreen();
    });

    it('shows a load error as an alert with a working Retry', async () => {
      api.get.mockRejectedValueOnce({ response: { data: { error: 'Admin access required' } } });
      render(<AdminScreen navigation={{ replace: jest.fn() }} />);
      await flush();
      expect(screen.getByText('Admin access required')).toBeOnTheScreen();
      expect(screen.getByRole('alert')).toBeOnTheScreen();

      api.get.mockResolvedValueOnce({ data: { organizations: ORGS, users: USERS } });
      press('Retry');
      await flush();
      expect(screen.queryByText('Admin access required')).toBeNull();
      expect(screen.getByLabelText('1 organizations')).toBeOnTheScreen();
    });

    it('marks the active tab as selected', async () => {
      await setup();
      expect(screen.getByRole('tab', { name: 'Dashboard' }).props.accessibilityState.selected).toBe(true);
      openTab('Users');
      expect(screen.getByRole('tab', { name: 'Users' }).props.accessibilityState.selected).toBe(true);
    });

    it('logs out: clears the session and returns to Login', async () => {
      await AsyncStorage.setItem('token', 't');
      await AsyncStorage.setItem('user', '{}');
      const navigation = await setup();
      press('Logout');
      await flush();
      expect(await AsyncStorage.getItem('token')).toBeNull();
      expect(await AsyncStorage.getItem('user')).toBeNull();
      expect(navigation.replace).toHaveBeenCalledWith('Login');
    });
  });

  describe('lists', () => {
    it('lists organizations and users', async () => {
      await setup();
      openTab('Organizations');
      expect(screen.getByText('Organizations (1)')).toBeOnTheScreen();
      expect(screen.getByText('Acme')).toBeOnTheScreen();
      openTab('Users');
      expect(screen.getByText('bob@acme.com')).toBeOnTheScreen();
      expect(screen.getByText('Org: Acme')).toBeOnTheScreen();
    });

    it('shows empty states', async () => {
      await setup({ orgs: [], users: [] });
      openTab('Organizations');
      expect(screen.getByText(/No organizations yet/)).toBeOnTheScreen();
      openTab('Users');
      expect(screen.getByText(/No users yet/)).toBeOnTheScreen();
    });

    it('supports pull to refresh', async () => {
      await setup();
      openTab('Users');
      api.get.mockClear();
      const list = screen.UNSAFE_getByType(FlatList);
      await act(async () => list.props.refreshControl.props.onRefresh());
      expect(api.get).toHaveBeenCalledWith('/admin/dashboard');
    });
  });

  describe('create user', () => {
    it('validates inline and does not call the API', async () => {
      await setup();
      openTab('Create User');
      press('Create user');
      expect(screen.getByText("Enter the user's email address.")).toBeOnTheScreen();
      expect(screen.getByText('Enter a password.')).toBeOnTheScreen();
      expect(screen.getByText('Select an organization.')).toBeOnTheScreen();
      expect(api.post).not.toHaveBeenCalled();

      fireEvent.changeText(input('Email'), 'bad');
      fireEvent.changeText(input('Password'), '123');
      press('Create user');
      expect(screen.getByText(/valid email/)).toBeOnTheScreen();
      expect(screen.getByText('Password must be at least 6 characters.')).toBeOnTheScreen();
    });

    it('creates the user, announces success and refreshes the dashboard', async () => {
      await setup();
      openTab('Create User');
      fireEvent.changeText(input('Email'), ' new@acme.com ');
      fireEvent.changeText(input('Password'), 'secret1');
      fireEvent.press(screen.getByRole('radio', { name: 'Acme' }));
      fireEvent.press(screen.getByRole('radio', { name: 'admin' }));
      api.post.mockResolvedValue({ data: { user: { email: 'new@acme.com' } } });
      press('Create user');
      await flush();

      expect(api.post).toHaveBeenCalledWith('/admin/users', {
        email: 'new@acme.com',
        password: 'secret1',
        org_id: 'o1',
        role: 'admin',
      });
      expect(screen.getByText('User "new@acme.com" created.')).toBeOnTheScreen();
      expect(api.get).toHaveBeenCalledTimes(2);
      // The form was reset.
      expect(input('Email').props.value).toBe('');
    });

    it('shows the backend error and keeps the form values', async () => {
      await setup();
      openTab('Create User');
      fireEvent.changeText(input('Email'), 'dup@acme.com');
      fireEvent.changeText(input('Password'), 'secret1');
      fireEvent.press(screen.getByRole('radio', { name: 'Acme' }));
      api.post.mockRejectedValue({ response: { data: { error: 'Email already exists' } } });
      press('Create user');
      await flush();
      expect(screen.getByText('Email already exists')).toBeOnTheScreen();
      expect(input('Email').props.value).toBe('dup@acme.com');
    });

    it('asks to create an organization first when there is none', async () => {
      await setup({ orgs: [], users: [] });
      openTab('Create User');
      expect(screen.getByText('Create an organization first.')).toBeOnTheScreen();
    });

    it('disables the submit button while the request is running', async () => {
      await setup();
      openTab('Create User');
      fireEvent.changeText(input('Email'), 'new@acme.com');
      fireEvent.changeText(input('Password'), 'secret1');
      fireEvent.press(screen.getByRole('radio', { name: 'Acme' }));
      let resolve;
      api.post.mockImplementation(() => new Promise((r) => { resolve = r; }));
      press('Create user');
      await flush();
      expect(screen.getByRole('button', { name: 'Create user' }).props.accessibilityState).toMatchObject({
        disabled: true,
        busy: true,
      });
      await act(async () => resolve({ data: { user: { email: 'new@acme.com' } } }));
    });
  });

  describe('create organization', () => {
    it('requires a name and the connector fields', async () => {
      await setup();
      openTab('Create Org');
      press('Create organization');
      expect(screen.getByText('Enter the organization name.')).toBeOnTheScreen();
      expect(screen.getByText('Host is required.')).toBeOnTheScreen();
      expect(screen.getByText('Password is required.')).toBeOnTheScreen();
      expect(api.post).not.toHaveBeenCalled();
    });

    it('creates an internal organization with an empty config', async () => {
      await setup();
      openTab('Create Org');
      fireEvent.changeText(input('Organization name'), 'Globex');
      fireEvent.press(screen.getByRole('radio', { name: 'Internal' }));
      api.post.mockResolvedValue({ data: { organization: { name: 'Globex' } } });
      press('Create organization');
      await flush();
      expect(api.post).toHaveBeenCalledWith('/admin/organizations', {
        name: 'Globex',
        industry: '',
        connector_type: 'internal',
        connector_config: {},
      });
      expect(screen.getByText('Organization "Globex" created.')).toBeOnTheScreen();
    });

    it('never sends a masked secret', async () => {
      await setup();
      openTab('Create Org');
      fireEvent.changeText(input('Organization name'), 'Globex');
      fireEvent.press(screen.getByRole('radio', { name: 'HubSpot' }));
      fireEvent.changeText(input('API Key'), '********');
      api.post.mockResolvedValue({ data: { organization: { name: 'Globex' } } });
      press('Create organization');
      await flush();
      expect(api.post.mock.calls[0][1].connector_config).toEqual({});
    });

    it('uses password fields with numeric and no-autofill keyboards for connector settings', async () => {
      await setup();
      openTab('Create Org');
      expect(input('Password').props.secureTextEntry).toBe(true);
      expect(input('Port').props.keyboardType).toBe('numeric');
      expect(input('Host').props.autoCapitalize).toBe('none');
    });
  });

  describe('delete', () => {
    const confirmButton = () => Alert.alert.mock.calls[0][2].find((b) => b.style === 'destructive');

    it('asks for confirmation before deleting a user and only then calls the API', async () => {
      await setup();
      openTab('Users');
      press('Delete bob@acme.com');
      expect(Alert.alert).toHaveBeenCalledWith('Delete user', 'Delete bob@acme.com?', expect.any(Array));
      expect(api.delete).not.toHaveBeenCalled();

      api.delete.mockResolvedValue({});
      await act(async () => confirmButton().onPress());
      expect(api.delete).toHaveBeenCalledWith('/admin/users/u1');
      expect(screen.getByText('User deleted.')).toBeOnTheScreen();
    });

    it('cancelling does nothing', async () => {
      await setup();
      openTab('Organizations');
      press('Delete Acme');
      const cancel = Alert.alert.mock.calls[0][2].find((b) => b.style === 'cancel');
      expect(cancel.onPress).toBeUndefined();
      expect(Alert.alert.mock.calls[0][1]).toMatch(/delete all its users/);
      expect(api.delete).not.toHaveBeenCalled();
    });

    it('deletes an organization after confirmation and reports failures', async () => {
      await setup();
      openTab('Organizations');
      press('Delete Acme');
      api.delete.mockRejectedValue({ response: { data: { error: 'Cannot delete' } } });
      await act(async () => confirmButton().onPress());
      expect(api.delete).toHaveBeenCalledWith('/admin/organizations/o1');
      expect(screen.getByText('Cannot delete')).toBeOnTheScreen();
    });
  });

  describe('edit organization', () => {
    const openEdit = async () => {
      await setup();
      openTab('Organizations');
      press('Edit Acme');
    };

    it('omits connector_config when it was not edited (stored secrets are not wiped)', async () => {
      await openEdit();
      fireEvent.changeText(input('Organization name'), 'Acme Inc');
      api.put.mockResolvedValue({});
      press('Save organization');
      await flush();
      expect(api.put).toHaveBeenCalledWith('/admin/organizations/o1', {
        name: 'Acme Inc',
        industry: 'Tech',
        connector_type: 'postgresql',
      });
      expect(api.put.mock.calls[0][1]).not.toHaveProperty('connector_config');
      expect(screen.getByText('Organization updated.')).toBeOnTheScreen();
    });

    it('sends only typed values and strips masked ones', async () => {
      await openEdit();
      fireEvent.changeText(input('Host'), 'new.example.com');
      fireEvent.changeText(input('Password'), '********');
      api.put.mockResolvedValue({});
      press('Save organization');
      await flush();
      expect(api.put.mock.calls[0][1].connector_config).toEqual({ host: 'new.example.com' });
    });

    it('requires the connector fields when the type changes', async () => {
      await openEdit();
      fireEvent.press(screen.getAllByRole('radio', { name: 'MySQL' })[0]);
      press('Save organization');
      expect(screen.getByText('Host is required.')).toBeOnTheScreen();
      expect(api.put).not.toHaveBeenCalled();
    });

    it('sends an empty config when switching to internal', async () => {
      await openEdit();
      fireEvent.press(screen.getAllByRole('radio', { name: 'Internal' })[0]);
      api.put.mockResolvedValue({});
      press('Save organization');
      await flush();
      expect(api.put.mock.calls[0][1]).toMatchObject({ connector_type: 'internal', connector_config: {} });
    });

    it('shows a failed update inside the open dialog', async () => {
      await openEdit();
      api.put.mockRejectedValue({ response: { data: { error: 'Name taken' } } });
      press('Save organization');
      await flush();
      expect(screen.getByText('Name taken')).toBeOnTheScreen();
    });

    it('validates the name and can be cancelled', async () => {
      await openEdit();
      fireEvent.changeText(input('Organization name'), ' ');
      press('Save organization');
      expect(screen.getByText('Enter the organization name.')).toBeOnTheScreen();
      press('Cancel');
      expect(screen.queryByText('Edit organization')).toBeNull();
    });
  });

  describe('edit user and reset password', () => {
    it('updates a user and maps an empty organization to null', async () => {
      await setup();
      openTab('Users');
      press('Edit bob@acme.com');
      fireEvent.changeText(input('Email'), 'bobby@acme.com');
      fireEvent.press(screen.getByRole('radio', { name: 'None' }));
      fireEvent.press(screen.getAllByRole('radio', { name: 'owner' })[0]);
      api.put.mockResolvedValue({});
      press('Save user');
      await flush();
      expect(api.put).toHaveBeenCalledWith('/admin/users/u1', {
        email: 'bobby@acme.com',
        role: 'owner',
        org_id: null,
      });
      expect(screen.getByText('User updated.')).toBeOnTheScreen();
    });

    it('validates the edited email', async () => {
      await setup();
      openTab('Users');
      press('Edit bob@acme.com');
      fireEvent.changeText(input('Email'), 'nope');
      press('Save user');
      expect(screen.getByText(/valid email/)).toBeOnTheScreen();
      expect(api.put).not.toHaveBeenCalled();
    });

    it('validates and submits a password reset', async () => {
      await setup();
      openTab('Users');
      press('Reset password for bob@acme.com');
      press('Reset password');
      expect(screen.getByText('Enter a new password.')).toBeOnTheScreen();
      fireEvent.changeText(input('New password'), '123');
      press('Reset password');
      expect(screen.getByText('Password must be at least 6 characters.')).toBeOnTheScreen();
      expect(api.put).not.toHaveBeenCalled();

      fireEvent.changeText(input('New password'), 'newsecret');
      api.put.mockResolvedValue({});
      press('Reset password');
      await flush();
      expect(api.put).toHaveBeenCalledWith('/admin/users/u1/reset-password', { password: 'newsecret' });
      expect(screen.getByText('Password reset for bob@acme.com.')).toBeOnTheScreen();
    });

    it('keeps the dialog open and shows the error when the reset fails', async () => {
      await setup();
      openTab('Users');
      press('Reset password for bob@acme.com');
      fireEvent.changeText(input('New password'), 'newsecret');
      api.put.mockRejectedValue({ response: { data: { error: 'Too weak' } } });
      press('Reset password');
      await flush();
      expect(screen.getByText('Too weak')).toBeOnTheScreen();
      expect(input('New password')).toBeOnTheScreen();
      press('Cancel');
      expect(screen.queryByLabelText(/^New password/)).toBeNull();
    });
  });

  it('clears the success message after a few seconds', async () => {
    await setup();
    openTab('Users');
    press('Delete bob@acme.com');
    api.delete.mockResolvedValue({});
    await act(async () => Alert.alert.mock.calls[0][2].find((b) => b.style === 'destructive').onPress());
    expect(screen.getByText('User deleted.')).toBeOnTheScreen();
    await act(async () => jest.advanceTimersByTime(5000));
    await waitFor(() => expect(screen.queryByText('User deleted.')).toBeNull());
  });
});
