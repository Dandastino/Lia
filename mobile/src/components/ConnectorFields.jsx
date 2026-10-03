import { useRef } from 'react';
import { Field } from './ui';
import { inputPropsFor } from '../lib/connector';

// Renders the inputs for a connector template. Defined at module level (not
// inside a screen) so typing does not remount the inputs and drop the keyboard.
export default function ConnectorFields({ fields, config, onChange, errors = {}, onSubmit, editable = true, hint }) {
  const refs = useRef({});

  return fields.map((f, index) => {
    const isLast = index === fields.length - 1;
    const next = fields[index + 1];
    return (
      <Field
        key={f.field}
        ref={(node) => {
          refs.current[f.field] = node;
        }}
        label={f.label}
        required={!!f.required}
        error={errors[f.field]}
        hint={index === 0 ? hint : undefined}
        value={String(config[f.field] ?? '')}
        onChangeText={(v) => onChange({ ...config, [f.field]: v })}
        placeholder={f.placeholder}
        editable={editable}
        returnKeyType={isLast ? 'done' : 'next'}
        blurOnSubmit={isLast}
        onSubmitEditing={() => (isLast ? onSubmit?.() : refs.current[next.field]?.focus())}
        {...inputPropsFor(f)}
      />
    );
  });
}
