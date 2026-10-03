import {
  CONNECTOR_CONFIG_TEMPLATES,
  CONNECTOR_LABELS,
  CONNECTOR_SETTINGS_TEMPLATES,
  CONNECTOR_TYPES,
  MASK,
  SETTINGS_CONNECTOR_TYPES,
  hasConfigValues,
  inputPropsFor,
  stripMaskedFields,
} from '../connector';

describe('connector helpers', () => {
  it('stripMaskedFields removes only masked values', () => {
    expect(stripMaskedFields({ host: 'h', password: MASK, api_key: MASK, port: 5432 })).toEqual({
      host: 'h',
      port: 5432,
    });
    expect(stripMaskedFields(undefined)).toEqual({});
  });

  it('stripMaskedFields does not mutate its input', () => {
    const input = { password: MASK };
    stripMaskedFields(input);
    expect(input).toEqual({ password: MASK });
  });

  it('hasConfigValues ignores blanks', () => {
    expect(hasConfigValues({ a: '', b: '  ', c: null })).toBe(false);
    expect(hasConfigValues({ a: '', b: 'x' })).toBe(true);
    expect(hasConfigValues(undefined)).toBe(false);
  });

  it('every selectable connector has a label and a template', () => {
    for (const type of CONNECTOR_TYPES) expect(CONNECTOR_LABELS[type]).toBeTruthy();
    for (const type of SETTINGS_CONNECTOR_TYPES) {
      expect(CONNECTOR_SETTINGS_TEMPLATES[type].length).toBeGreaterThan(0);
      expect(CONNECTOR_CONFIG_TEMPLATES[type].length).toBeGreaterThan(0);
    }
    expect(CONNECTOR_TYPES).toContain('internal');
    expect(SETTINGS_CONNECTOR_TYPES).not.toContain('internal');
  });

  it('inputPropsFor maps field types to keyboard / secure props', () => {
    expect(inputPropsFor({ type: 'password' }).secureTextEntry).toBe(true);
    expect(inputPropsFor({ type: 'number' }).keyboardType).toBe('numeric');
    expect(inputPropsFor({ type: 'url' }).keyboardType).toBe('url');
    const text = inputPropsFor({ type: 'text' });
    expect(text).toMatchObject({ secureTextEntry: false, keyboardType: 'default', autoCapitalize: 'none' });
  });
});
