import { act, render, screen } from '@testing-library/react-native';
import { NavigationContainer } from '@react-navigation/native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import AppNavigator from '../AppNavigator';
import { navigationRef } from '../navigationRef';
import { handleResponseError } from '../../lib/api';

// Function declarations are hoisted, so jest.mock factories (hoisted above the
// imports) can use them. The real screens pull in LiveKit and are tested separately.
function mockScreen(label) {
  return () => require('react').createElement(require('react-native').Text, null, label);
}

jest.mock('../../screens/LoginScreen', () => mockScreen('Login screen'));
jest.mock('../../screens/VoiceScreen', () => mockScreen('Voice screen'));
jest.mock('../../screens/AdminScreen', () => mockScreen('Admin screen'));
jest.mock('../../screens/ConnectorSettingsScreen', () => mockScreen('Settings screen'));

// The real ref only becomes ready inside a mounted native container; a stub lets
// us assert exactly what the 401 handler asks the navigation to do.
jest.mock('../navigationRef', () => ({
  navigationRef: { isReady: jest.fn(() => true), reset: jest.fn() },
}));

const renderApp = () =>
  render(
    <NavigationContainer>
      <AppNavigator />
    </NavigationContainer>,
  );

describe('AppNavigator', () => {
  beforeEach(() => jest.clearAllMocks());

  it('shows a loading indicator, then Login without a session', async () => {
    renderApp();
    expect(screen.getByLabelText('Loading')).toBeOnTheScreen();
    expect(await screen.findByText('Login screen')).toBeOnTheScreen();
  });

  it.each([
    ['admin', 'Admin screen'],
    ['owner', 'Admin screen'],
    ['user', 'Voice screen'],
  ])('restores a stored %s session to %s', async (role, text) => {
    await AsyncStorage.setItem('token', 'jwt');
    await AsyncStorage.setItem('user', JSON.stringify({ id: '1', role }));
    renderApp();
    expect(await screen.findByText(text)).toBeOnTheScreen();
  });

  it('falls back to Login when the stored user is corrupted', async () => {
    await AsyncStorage.setItem('token', 'jwt');
    await AsyncStorage.setItem('user', '{broken');
    renderApp();
    expect(await screen.findByText('Login screen')).toBeOnTheScreen();
  });

  it('falls back to Login when only one half of the session exists', async () => {
    await AsyncStorage.setItem('user', JSON.stringify({ role: 'admin' }));
    renderApp();
    expect(await screen.findByText('Login screen')).toBeOnTheScreen();
  });

  it('resets navigation to Login and clears the session when a request gets a 401', async () => {
    await AsyncStorage.setItem('token', 'jwt');
    await AsyncStorage.setItem('user', JSON.stringify({ id: '1', role: 'admin' }));
    renderApp();
    expect(await screen.findByText('Admin screen')).toBeOnTheScreen();

    await act(async () => {
      await handleResponseError({ response: { status: 401 }, config: { url: '/admin/dashboard' } }).catch(() => {});
    });

    expect(navigationRef.reset).toHaveBeenCalledWith({ index: 0, routes: [{ name: 'Login' }] });
    expect(await AsyncStorage.getItem('token')).toBeNull();
    expect(await AsyncStorage.getItem('user')).toBeNull();
  });

  it('does nothing on a 401 while the navigator is not ready yet', async () => {
    navigationRef.isReady.mockReturnValueOnce(false);
    renderApp();
    await screen.findByText('Login screen');
    await act(async () => {
      await handleResponseError({ response: { status: 401 }, config: { url: '/x' } }).catch(() => {});
    });
    expect(navigationRef.reset).not.toHaveBeenCalled();
  });
});
