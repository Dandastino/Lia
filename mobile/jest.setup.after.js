import '@testing-library/react-native/extend-expect';
import AsyncStorage from '@react-native-async-storage/async-storage';

// Fresh storage for every test.
beforeEach(async () => {
  await AsyncStorage.clear();
});
