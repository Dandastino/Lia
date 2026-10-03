import { StyleSheet } from 'react-native';
import { colors, MIN_TOUCH } from '../theme';

export const waveStyles = StyleSheet.create({
  container: { flexDirection: 'row', alignItems: 'center', gap: 4, height: 60 },
  bar: { width: 6, height: 40, borderRadius: 3 },
});

export const statusStyles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  text: { fontSize: 14 },
});

export const styles = StyleSheet.create({
  flex: { flex: 1 },
  loadingContainer: {
    flex: 1,
    backgroundColor: colors.background,
    justifyContent: 'center',
    alignItems: 'center',
  },
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  //── Header ──
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: colors.background,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  headerTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: colors.text,
    letterSpacing: 1,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexShrink: 1,
    maxWidth: '75%',
  },
  headerUser: {
    color: colors.textSecondary,
    fontSize: 13,
    flexShrink: 1,
  },
  headerBtn: {
    minWidth: MIN_TOUCH,
    minHeight: MIN_TOUCH,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerBtnText: {
    fontSize: 20,
  },
  logoutBtn: {
    backgroundColor: colors.surfaceRaised,
    minHeight: MIN_TOUCH,
    justifyContent: 'center',
    paddingHorizontal: 12,
    borderRadius: 8,
  },
  logoutBtnText: {
    color: colors.textSecondary,
    fontSize: 13,
  },
  //── Content ──
  content: {
    flex: 1,
  },
  centerContent: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
  },
  connectingText: {
    color: colors.textSecondary,
    fontSize: 15,
    marginTop: 12,
  },
  reconnectBtn: {
    backgroundColor: colors.primaryStrong,
    minHeight: MIN_TOUCH,
    paddingHorizontal: 32,
    paddingVertical: 16,
    borderRadius: 12,
  },
  reconnectBtnText: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '600',
  },
  errorBanner: {
    backgroundColor: colors.dangerBg,
    borderColor: colors.dangerBorder,
    borderWidth: 1,
    margin: 12,
    borderRadius: 10,
    padding: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  errorBannerText: {
    color: colors.danger,
    fontSize: 14,
    flex: 1,
  },
  retryBtn: {
    backgroundColor: colors.primaryStrong,
    minHeight: MIN_TOUCH,
    justifyContent: 'center',
    paddingHorizontal: 16,
    borderRadius: 8,
    marginLeft: 8,
  },
  retryBtnText: {
    color: colors.text,
    fontSize: 13,
    fontWeight: '600',
  },
  //── Conversation Box ──
  conversationBox: {
    flex: 1,
    backgroundColor: colors.panel,
    margin: 12,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    overflow: 'hidden',
  },
  conversationHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  conversationTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.text,
  },
  //── Messages ──
  messagesList: {
    flex: 1,
  },
  messagesContent: {
    padding: 12,
    flexGrow: 1,
  },
  message: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    marginVertical: 4,
    maxWidth: '85%',
  },
  userMessage: {
    alignSelf: 'flex-end',
    flexDirection: 'row-reverse',
  },
  aiMessage: {
    alignSelf: 'flex-start',
  },
  typingMessage: {
    opacity: 0.8,
  },
  messageAvatar: {
    fontSize: 20,
    marginTop: 2,
  },
  messageText: {
    color: colors.text,
    fontSize: 14,
    lineHeight: 20,
    backgroundColor: colors.borderSubtle,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
    overflow: 'hidden',
    flexShrink: 1,
  },
  cursor: {
    color: colors.primary,
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
    gap: 16,
    minHeight: 200,
  },
  waveLabel: {
    color: colors.textSecondary,
    fontSize: 14,
  },
  emptyHint: {
    color: colors.textMuted,
    fontSize: 14,
    textAlign: 'center',
    marginTop: 8,
  },
  //── Controls ──
  controls: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 16,
    padding: 16,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
  },
  controlBtn: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 80,
    height: 80,
    borderRadius: 40,
    gap: 4,
  },
  micActive: {
    backgroundColor: colors.micOnBg,
    borderWidth: 2,
    borderColor: colors.success,
  },
  micMuted: {
    backgroundColor: colors.micOffBg,
    borderWidth: 2,
    borderColor: colors.danger,
  },
  disconnectBtn: {
    backgroundColor: colors.micOffBg,
    borderWidth: 2,
    borderColor: colors.danger,
  },
  controlBtnIcon: {
    fontSize: 24,
  },
  controlBtnLabel: {
    color: colors.textSecondary,
    fontSize: 12,
  },
});
