import { useState } from 'react';
import { Button, Field } from '../../components/ui';
import { MIN_PASSWORD_LENGTH, validateNewPassword } from '../../lib/validation';
import FormModal from './FormModal';

export default function ResetPasswordModal({ user, busy, error: serverError, onSubmit, onClose }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = () => {
    if (busy) return;
    const message = validateNewPassword(password);
    setError(message);
    if (!message) onSubmit(password);
  };

  return (
    <FormModal visible={!!user} title="Reset password" subtitle={user?.email} error={serverError} onClose={onClose}>
      <Field
        label="New password"
        required
        error={error}
        hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="new-password"
        textContentType="newPassword"
        returnKeyType="done"
        onSubmitEditing={handleSubmit}
        editable={!busy}
      />
      <Button label="Reset password" onPress={handleSubmit} loading={busy} loadingLabel="Resetting" />
      <Button label="Cancel" variant="secondary" onPress={onClose} disabled={busy} style={{ marginTop: 12 }} />
    </FormModal>
  );
}
