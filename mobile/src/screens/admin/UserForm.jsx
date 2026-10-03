import { useRef, useState } from 'react';
import { Button, ChoiceChips, Field } from '../../components/ui';
import { MIN_PASSWORD_LENGTH, validateEditUser, validateNewUser } from '../../lib/validation';

export const ROLE_OPTIONS = ['user', 'owner', 'admin'].map((value) => ({ value, label: value }));

/** Create / edit user form (mode is 'create' or 'edit'). */
export default function UserForm({ mode, initial, organizations, busy, onSubmit, onCancel }) {
  const isCreate = mode === 'create';
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const passwordRef = useRef(null);

  const orgOptions = [
    ...(isCreate ? [] : [{ value: '', label: 'None' }]),
    ...organizations.map((o) => ({ value: o.id, label: o.name })),
  ];

  const handleSubmit = () => {
    if (busy) return;
    const nextErrors = isCreate ? validateNewUser(form) : validateEditUser(form);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    onSubmit(form);
  };

  return (
    <>
      <Field
        label="Email"
        required
        error={errors.email}
        value={form.email}
        onChangeText={(email) => setForm((p) => ({ ...p, email }))}
        placeholder="user@example.com"
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="email"
        textContentType="emailAddress"
        returnKeyType={isCreate ? 'next' : 'done'}
        blurOnSubmit={!isCreate}
        onSubmitEditing={() => (isCreate ? passwordRef.current?.focus() : handleSubmit())}
        editable={!busy}
      />
      {isCreate && (
        <Field
          ref={passwordRef}
          label="Password"
          required
          error={errors.password}
          hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          value={form.password}
          onChangeText={(password) => setForm((p) => ({ ...p, password }))}
          secureTextEntry
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="new-password"
          textContentType="newPassword"
          returnKeyType="done"
          onSubmitEditing={handleSubmit}
          editable={!busy}
        />
      )}
      <ChoiceChips
        label="Role"
        options={ROLE_OPTIONS}
        value={form.role}
        onChange={(role) => setForm((p) => ({ ...p, role }))}
      />
      <ChoiceChips
        label="Organization"
        options={orgOptions}
        value={form.org_id || ''}
        onChange={(org_id) => setForm((p) => ({ ...p, org_id }))}
        error={errors.org_id || (isCreate && organizations.length === 0 ? 'Create an organization first.' : undefined)}
      />
      <Button
        label={isCreate ? 'Create user' : 'Save user'}
        onPress={handleSubmit}
        loading={busy}
        loadingLabel={isCreate ? 'Creating' : 'Saving'}
      />
      {onCancel && <Button label="Cancel" variant="secondary" onPress={onCancel} disabled={busy} style={{ marginTop: 12 }} />}
    </>
  );
}
