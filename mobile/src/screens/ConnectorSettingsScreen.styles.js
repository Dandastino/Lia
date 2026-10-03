import { StyleSheet } from 'react-native';
import { colors, spacing, MIN_TOUCH } from '../theme';

export const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
    gap: spacing.md,
  },
  backBtn: { minHeight: MIN_TOUCH, minWidth: MIN_TOUCH, justifyContent: 'center' },
  backBtnText: { color: colors.primary, fontSize: 16 },
  headerTitle: { fontSize: 18, fontWeight: '600', color: colors.text },
  content: { padding: 20, paddingBottom: 48 },
  subtitle: { color: colors.textSecondary, fontSize: 14, marginBottom: spacing.xl, lineHeight: 20 },
  loadingRow: { alignItems: 'center', marginBottom: spacing.lg },
});
