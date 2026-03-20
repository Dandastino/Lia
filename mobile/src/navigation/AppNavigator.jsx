import React, { useState, useEffect } from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { storage } from '../lib/storage';
import LoginScreen from '../screens/LoginScreen';
import VoiceScreen from '../screens/VoiceScreen';
import AdminScreen from '../screens/AdminScreen';
import ConnectorSettingsScreen from '../screens/ConnectorSettingsScreen';

const Stack = createNativeStackNavigator();

export default function AppNavigator() {
  const [initialRoute, setInitialRoute] = useState(null);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const token = await storage.getItem('token');
        const userStr = await storage.getItem('user');
        if (token && userStr) {
          const user = JSON.parse(userStr);
          const isAdmin = user.role === 'admin' || user.role === 'owner';
          setInitialRoute(isAdmin ? 'Admin' : 'Voice');
        } else {
          setInitialRoute('Login');
        }
      } catch {
        setInitialRoute('Login');
      }
    };
    checkAuth();
  }, []);

  if (!initialRoute) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator size="large" color="#6c63ff" />
      </View>
    );
  }

  return (
    <Stack.Navigator
      initialRouteName={initialRoute}
      screenOptions={{ headerShown: false }}
    >
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
    backgroundColor: '#0f0f1a',
    justifyContent: 'center',
    alignItems: 'center',
  },
});
