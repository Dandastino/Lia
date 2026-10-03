import React from 'react';
import { ActivityIndicator, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { colors } from '../theme';
import { styles } from './ui.styles';

const VARIANT_STYLES = {
  primary: [styles.buttonPrimary, styles.buttonTextPrimary],
  secondary: [styles.buttonSecondary, styles.buttonTextSecondary],
  danger: [styles.buttonDanger, styles.buttonTextDanger],
  ghost: [styles.buttonGhost, styles.buttonTextGhost],
};

// Accessible button: >= 44pt tall, announces busy/disabled, never fires while busy.
export function Button({
  label,
  onPress,
  loading = false,
  loadingLabel,
  disabled = false,
  variant = 'primary',
  accessibilityHint,
  accessibilityLabel,
  style,
  testID,
}) {
  const [buttonStyle, textStyle] = VARIANT_STYLES[variant] || VARIANT_STYLES.primary;
  const inactive = disabled || loading;
  return (
    <TouchableOpacity
      style={[styles.button, buttonStyle, inactive && styles.buttonDisabled, style]}
      onPress={onPress}
      disabled={inactive}
      activeOpacity={0.8}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel || label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: inactive, busy: loading }}
      hitSlop={{ top: 4, bottom: 4, left: 4, right: 4 }}
      testID={testID}
    >
      {loading ? (
        <ActivityIndicator color={colors.onPrimary} accessibilityLabel={loadingLabel || 'Loading'} />
      ) : (
        <Text style={[styles.buttonText, textStyle]}>{label}</Text>
      )}
    </TouchableOpacity>
  );
}

// Labelled text input with inline error + hint. The error is a live region so
// screen readers announce it when it appears.
export const Field = React.forwardRef(function Field(
  { label, required = false, error, hint, style, ...inputProps },
  ref,
) {
  return (
    <View style={styles.field}>
      <Text style={styles.label} accessibilityElementsHidden importantForAccessibility="no">
        {label}
        {required ? <Text style={styles.required}> *</Text> : null}
      </Text>
      <TextInput
        ref={ref}
        style={[styles.input, !!error && styles.inputError, style]}
        placeholderTextColor={colors.placeholder}
        accessibilityLabel={required ? `${label}, required` : label}
        accessibilityHint={hint}
        accessibilityState={{ disabled: inputProps.editable === false }}
        {...inputProps}
      />
      {!!hint && !error && <Text style={styles.hint}>{hint}</Text>}
      {!!error && (
        <Text style={styles.fieldError} accessibilityLiveRegion="polite" accessibilityRole="alert">
          {error}
        </Text>
      )}
    </View>
  );
});

// Error / success message. Always announced to screen readers.
export function Banner({ kind = 'error', message }) {
  if (!message) return null;
  const isError = kind === 'error';
  return (
    <View
      style={[styles.banner, isError ? styles.bannerError : styles.bannerSuccess]}
      accessible
      accessibilityLiveRegion={isError ? 'assertive' : 'polite'}
      accessibilityRole={isError ? 'alert' : undefined}
    >
      <Text style={[styles.bannerText, isError ? styles.bannerTextError : styles.bannerTextSuccess]}>
        {message}
      </Text>
    </View>
  );
}

// Single-select list of chips (radio group semantics).
export function ChoiceChips({ label, options, value, onChange, error }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label} accessibilityRole="header">{label}</Text>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipRow}
        keyboardShouldPersistTaps="handled"
        accessibilityRole="radiogroup"
        accessibilityLabel={label}
      >
        {options.map((opt) => {
          const selected = opt.value === value;
          return (
            <TouchableOpacity
              key={String(opt.value)}
              style={[styles.chip, selected && styles.chipActive]}
              onPress={() => onChange(opt.value)}
              accessibilityRole="radio"
              accessibilityLabel={opt.label}
              accessibilityState={{ selected, checked: selected }}
              activeOpacity={0.8}
            >
              <Text style={[styles.chipText, selected && styles.chipTextActive]}>{opt.label}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
      {!!error && (
        <Text style={styles.fieldError} accessibilityLiveRegion="polite" accessibilityRole="alert">
          {error}
        </Text>
      )}
    </View>
  );
}
