import { StyleSheet } from 'react-native';

export const waveStyles = StyleSheet.create({
  container: { flexDirection: 'row', alignItems: 'center', gap: 4, height: 60 },
  bar: { width: 6, height: 40, borderRadius: 3 },
});

export const statusStyles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  text: { fontSize: 13 },
});

export const styles = StyleSheet.create({
  flex: { flex: 1 },
  loadingContainer: {
    flex: 1,
    backgroundColor: '#0f0f1a',
    justifyContent: 'center',
    alignItems: 'center',
  },
  container: {
    flex: 1,
    backgroundColor: '#0f0f1a',
  },
  //── Header ──
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#0f0f1a',
    borderBottomWidth: 1,
    borderBottomColor: '#1e1e3a',
  },
  headerTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#fff',
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
    color: '#aaa',
    fontSize: 12,
    flexShrink: 1,
  },
  headerBtn: {
    padding: 6,
  },
  headerBtnText: {
    fontSize: 20,
  },
  logoutBtn: {
    backgroundColor: '#2a2a4a',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  logoutBtnText: {
    color: '#ccc',
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
    color: '#aaa',
    fontSize: 15,
    marginTop: 12,
  },
  reconnectBtn: {
    backgroundColor: '#667eea',
    paddingHorizontal: 32,
    paddingVertical: 16,
    borderRadius: 12,
  },
  reconnectBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  errorBanner: {
    backgroundColor: 'rgba(239,68,68,0.1)',
    borderColor: 'rgba(239,68,68,0.3)',
    borderWidth: 1,
    margin: 12,
    borderRadius: 10,
    padding: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  errorBannerText: {
    color: '#ef4444',
    fontSize: 13,
    flex: 1,
  },
  retryBtn: {
    backgroundColor: '#667eea',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    marginLeft: 8,
  },
  retryBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  //── Conversation Box ──
  conversationBox: {
    flex: 1,
    backgroundColor: '#12121f',
    margin: 12,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#1e1e3a',
    overflow: 'hidden',
  },
  conversationHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#1e1e3a',
  },
  conversationTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
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
    color: '#e0e0e0',
    fontSize: 14,
    lineHeight: 20,
    backgroundColor: '#1e1e3a',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 8,
    overflow: 'hidden',
    flexShrink: 1,
  },
  cursor: {
    color: '#667eea',
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
    color: '#aaa',
    fontSize: 14,
  },
  emptyHint: {
    color: '#555',
    fontSize: 13,
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
    borderTopColor: '#1e1e3a',
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
    backgroundColor: '#1a2a3a',
    borderWidth: 2,
    borderColor: '#10b981',
  },
  micMuted: {
    backgroundColor: '#2a1a1a',
    borderWidth: 2,
    borderColor: '#ef4444',
  },
  disconnectBtn: {
    backgroundColor: '#2a1a1a',
    borderWidth: 2,
    borderColor: '#ef4444',
  },
  controlBtnIcon: {
    fontSize: 24,
  },
  controlBtnLabel: {
    color: '#aaa',
    fontSize: 11,
  },
});
