import { Text, TextInput } from 'react-native';
import { MAX_FONT_SCALE } from '../theme';

// Respect the user's system font size but cap it so fixed-height controls and
// headers do not overflow at the largest accessibility settings.
export function applyFontScaleCap() {
  Text.defaultProps = { ...(Text.defaultProps || {}), allowFontScaling: true, maxFontSizeMultiplier: MAX_FONT_SCALE };
  TextInput.defaultProps = {
    ...(TextInput.defaultProps || {}),
    allowFontScaling: true,
    maxFontSizeMultiplier: MAX_FONT_SCALE,
  };
}
