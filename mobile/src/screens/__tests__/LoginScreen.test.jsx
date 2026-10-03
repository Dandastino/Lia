import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import LoginScreen from '../LoginScreen';
import { api } from '../../lib/api';

jest.mock('../../lib/api', () => ({
  ...jest.requireActual('../../lib/api'),
  api: { post: jest.fn() },
}));

const setup = () => {
  const navigation = { replace: jest.fn() };
  render(<LoginScreen navigation={navigation} />);
  return navigation;
};

const fill = (email, password) => {
  fireEvent.changeText(screen.getByLabelText(/^Email/), email);
  fireEvent.changeText(screen.getByLabelText(/^Password/), password);
};

describe('LoginScreen', () => {
  beforeEach(() => jest.clearAllMocks());

  it('labels its controls and sets keyboard / autofill hints', () => {
    setup();
    const email = screen.getByLabelText(/^Email/);
    expect(email.props.keyboardType).toBe('email-address');
    expect(email.props.autoComplete).toBe('email');
    expect(email.props.textContentType).toBe('username');
    expect(email.props.returnKeyType).toBe('next');
    const password = screen.getByLabelText(/^Password/);
    expect(password.props.secureTextEntry).toBe(true);
    expect(password.props.autoComplete).toBe('current-password');
    expect(password.props.returnKeyType).toBe('go');
    expect(screen.getByRole('button', { name: 'Login' })).toBeOnTheScreen();
  });

  it.each([
    ['admin', 'Admin'],
    ['owner', 'Admin'],
    ['user', 'Voice'],
  ])('stores the session and routes a %s to %s', async (role, route) => {
    const user = { id: '1', email: 'a@b.co', role };
    api.post.mockResolvedValue({ data: { access_token: 'jwt', user } });
    const navigation = setup();
    fill('  a@b.co ', 'secret1');
    fireEvent.press(screen.getByRole('button', { name: 'Login' }));

    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith(route));
    expect(api.post).toHaveBeenCalledWith('/login', { email: 'a@b.co', password: 'secret1' });
    expect(await AsyncStorage.getItem('token')).toBe('jwt');
    expect(JSON.parse(await AsyncStorage.getItem('user'))).toEqual(user);
  });

  it('submits from the keyboard "go" key', async () => {
    api.post.mockResolvedValue({ data: { access_token: 'jwt', user: { role: 'user' } } });
    const navigation = setup();
    fill('a@b.co', 'secret1');
    fireEvent(screen.getByLabelText(/^Password/), 'submitEditing');
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith('Voice'));
  });

  it('shows inline validation errors and does not call the API', () => {
    setup();
    fireEvent.press(screen.getByRole('button', { name: 'Login' }));
    expect(screen.getByText('Enter your email address.')).toBeOnTheScreen();
    expect(screen.getByText('Enter your password.')).toBeOnTheScreen();
    fireEvent.changeText(screen.getByLabelText(/^Email/), 'not-an-email');
    fireEvent.press(screen.getByRole('button', { name: 'Login' }));
    expect(screen.getByText(/Enter a valid email address/)).toBeOnTheScreen();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('announces wrong credentials as an alert and keeps the user on the screen', async () => {
    api.post.mockRejectedValue({ response: { status: 401, data: { error: 'Invalid email or password' } } });
    const navigation = setup();
    fill('a@b.co', 'wrongpw');
    fireEvent.press(screen.getByRole('button', { name: 'Login' }));

    expect(await screen.findByText('Invalid email or password')).toBeOnTheScreen();
    expect(screen.getByRole('alert').props.accessibilityLiveRegion).toBe('assertive');
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(await AsyncStorage.getItem('token')).toBeNull();
    // The form is usable again.
    expect(screen.getByRole('button', { name: 'Login' }).props.accessibilityState.disabled).toBe(false);
  });

  it('reports an unreachable server', async () => {
    api.post.mockRejectedValue({ request: {} });
    setup();
    fill('a@b.co', 'secret1');
    fireEvent.press(screen.getByRole('button', { name: 'Login' }));
    expect(await screen.findByText(/Cannot reach the server/)).toBeOnTheScreen();
  });

  it('rejects a malformed server response', async () => {
    api.post.mockResolvedValue({ data: {} });
    const navigation = setup();
    fill('a@b.co', 'secret1');
    fireEvent.press(screen.getByRole('button', { name: 'Login' }));
    expect(await screen.findByText('Invalid response from server.')).toBeOnTheScreen();
    expect(navigation.replace).not.toHaveBeenCalled();
  });

  it('disables the button while submitting and ignores double taps', async () => {
    let resolve;
    api.post.mockImplementation(() => new Promise((r) => { resolve = r; }));
    const navigation = setup();
    fill('a@b.co', 'secret1');
    const button = () => screen.getByRole('button', { name: 'Login' });
    fireEvent.press(button());
    await waitFor(() => expect(button().props.accessibilityState).toMatchObject({ disabled: true, busy: true }));
    fireEvent.press(button());
    expect(api.post).toHaveBeenCalledTimes(1);

    resolve({ data: { access_token: 'jwt', user: { role: 'user' } } });
    await waitFor(() => expect(navigation.replace).toHaveBeenCalled());
  });
});
