import { StyleSheet } from 'react-native';
import { colors, radius, spacing, MIN_TOUCH } from '../theme';

export const styles = StyleSheet.create({
  // Button
  button: {
    minHeight: MIN_TOUCH,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonPrimary: { backgroundColor: colors.primaryStrong },
  buttonSecondary: { backgroundColor: colors.surfaceRaised },
  buttonDanger: { backgroundColor: colors.dangerBg, borderWidth: 1, borderColor: colors.dangerBorder },
  buttonGhost: { backgroundColor: 'transparent' },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { fontSize: 16, fontWeight: '600' },
  buttonTextPrimary: { color: colors.onPrimary },
  buttonTextSecondary: { color: colors.text },
  buttonTextDanger: { color: colors.danger },
  buttonTextGhost: { color: colors.primary },

  // Field
  field: { marginBottom: spacing.lg },
  label: { color: colors.textSecondary, fontSize: 14, marginBottom: 6 },
  required: { color: colors.danger },
  input: {
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    color: colors.text,
    paddingHorizontal: 14,
    paddingVertical: 12,
    minHeight: MIN_TOUCH,
    fontSize: 16,
  },
  inputError: { borderColor: colors.danger },
  hint: { color: colors.textMuted, fontSize: 13, marginTop: 4 },
  fieldError: { color: colors.danger, fontSize: 13, marginTop: 4 },

  // Banner
  banner: { borderRadius: radius.sm, padding: spacing.md, marginBottom: spacing.lg, borderWidth: 1 },
  bannerError: { backgroundColor: colors.dangerBg, borderColor: colors.dangerBorder },
  bannerSuccess: { backgroundColor: colors.successBg, borderColor: colors.successBorder },
  bannerText: { fontSize: 14, textAlign: 'center' },
  bannerTextError: { color: colors.danger },
  bannerTextSuccess: { color: colors.success },

  // Chips
  chipRow: { flexGrow: 0 },
  chip: {
    minHeight: MIN_TOUCH,
    justifyContent: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.lg,
    marginRight: spacing.sm,
  },
  chipActive: { backgroundColor: colors.primaryStrong, borderColor: colors.primaryStrong },
  chipText: { color: colors.textSecondary, fontSize: 14 },
  chipTextActive: { color: colors.onPrimary, fontWeight: '600' },
});
