// Must be first import — polyfill crypto.getRandomValues for LiveKit on Android
import 'react-native-get-random-values';
import { registerRootComponent } from 'expo';
import App from './App';

registerRootComponent(App);
