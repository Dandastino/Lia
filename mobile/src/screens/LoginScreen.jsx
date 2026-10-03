import { useRef, useState } from 'react';
import { View, Text, KeyboardAvoidingView, Platform, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api, getErrorMessage } from '../lib/api';
import { saveSession, homeRouteFor } from '../lib/storage';
import { validateLogin } from '../lib/validation';
import { Banner, Button, Field } from '../components/ui';
import { styles } from './LoginScreen.styles';

export default function LoginScreen({ navigation }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const passwordRef = useRef(null);

  const handleLogin = async () => {
    if (loading) return;
    const errors = validateLogin({ email, password });
    setFieldErrors(errors);
    setError('');
    if (Object.keys(errors).length > 0) return;

    setLoading(true);
    try {
      const response = await api.post('/login', { email: email.trim(), password });
      if (response.data.access_token && response.data.user) {
        const user = response.data.user;
        await saveSession(response.data.access_token, user);
        navigation.replace(homeRouteFor(user));
      } else {
        setError('Invalid response from server.');
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Sign in failed. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
          <View style={styles.box}>
            <Text style={styles.title} accessibilityRole="header">Lia</Text>
            <Text style={styles.subtitle}>Sign in to your account</Text>

            <Banner kind="error" message={error} />

            <Field
              label="Email"
              value={email}
              onChangeText={setEmail}
              error={fieldErrors.email}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="email"
              textContentType="username"
              returnKeyType="next"
              blurOnSubmit={false}
              onSubmitEditing={() => passwordRef.current?.focus()}
              placeholder="your@email.com"
              editable={!loading}
            />

            <Field
              ref={passwordRef}
              label="Password"
              value={password}
              onChangeText={setPassword}
              error={fieldErrors.password}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="current-password"
              textContentType="password"
              returnKeyType="go"
              onSubmitEditing={handleLogin}
              placeholder="Your password"
              editable={!loading}
            />

            <Button
              label="Login"
              onPress={handleLogin}
              loading={loading}
              loadingLabel="Signing in"
              accessibilityHint="Signs in with the email and password above"
              style={styles.submit}
            />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
