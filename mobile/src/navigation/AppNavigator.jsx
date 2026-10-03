import { useState, useEffect } from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { getStoredUser, getToken, homeRouteFor } from '../lib/storage';
import { onUnauthorized } from '../lib/api';
import { colors } from '../theme';
import { navigationRef } from './navigationRef';
import LoginScreen from '../screens/LoginScreen';
import VoiceScreen from '../screens/VoiceScreen';
import AdminScreen from '../screens/AdminScreen';
import ConnectorSettingsScreen from '../screens/ConnectorSettingsScreen';

const Stack = createNativeStackNavigator();

export default function AppNavigator() {
  const [initialRoute, setInitialRoute] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const checkAuth = async () => {
      const token = await getToken();
      const user = token ? await getStoredUser() : null;
      if (!cancelled) setInitialRoute(user ? homeRouteFor(user) : 'Login');
    };
    checkAuth();
    return () => {
      cancelled = true;
    };
  }, []);

  // An expired/invalid session (HTTP 401) clears storage in lib/api; send the
  // user back to Login and drop the navigation history.
  useEffect(
    () =>
      onUnauthorized(() => {
        if (navigationRef.isReady()) {
          navigationRef.reset({ index: 0, routes: [{ name: 'Login' }] });
        }
      }),
    [],
  );

  if (!initialRoute) {
    return (
      <View style={styles.loading} accessibilityLabel="Loading" accessibilityLiveRegion="polite">
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <Stack.Navigator initialRouteName={initialRoute} screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Login" component={LoginScreen} />
      <Stack.Screen name="Voice" component={VoiceScreen} />
      <Stack.Screen name="Admin" component={AdminScreen} />
      <Stack.Screen name="ConnectorSettings" component={ConnectorSettingsScreen} />
    </Stack.Navigator>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    backgroundColor: colors.background,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
