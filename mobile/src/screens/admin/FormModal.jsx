import { KeyboardAvoidingView, Modal, Platform, ScrollView, Text, View } from 'react-native';
import { Banner } from '../../components/ui';
import { styles } from '../AdminScreen.styles';

// Bottom-sheet modal that keeps its fields above the keyboard.
export default function FormModal({ visible, title, subtitle, error, onClose, children }) {
  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <KeyboardAvoidingView
        style={styles.modalOverlay}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <View style={styles.modalBox} accessibilityViewIsModal>
          <Text style={styles.modalTitle} accessibilityRole="header">{title}</Text>
          {!!subtitle && <Text style={styles.modalSubtitle}>{subtitle}</Text>}
          <Banner kind="error" message={error} />
          <ScrollView keyboardShouldPersistTaps="handled">{children}</ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
