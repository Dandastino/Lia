import { Text, TextInput } from 'react-native';
import { colors, contrastRatio, hitSlopFor, luminance, MAX_FONT_SCALE, MIN_TOUCH } from '../theme';
import { applyFontScaleCap } from '../lib/fontScaling';

describe('theme', () => {
  const AA = 4.5;
  const surfaces = [colors.background, colors.surface, colors.panel, colors.surfaceRaised];

  it.each(surfaces)('body and muted text meet WCAG AA on %s', (bg) => {
    for (const fg of [colors.text, colors.textSecondary, colors.textMuted]) {
      expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(AA);
    }
  });

  it('accent, danger and success text are readable on the dark surfaces', () => {
    for (const bg of [colors.background, colors.surface]) {
      expect(contrastRatio(colors.primary, bg)).toBeGreaterThanOrEqual(AA);
      expect(contrastRatio(colors.danger, bg)).toBeGreaterThanOrEqual(AA);
      expect(contrastRatio(colors.success, bg)).toBeGreaterThanOrEqual(AA);
      expect(contrastRatio(colors.placeholder, bg)).toBeGreaterThanOrEqual(AA);
    }
  });

  it('white text on the primary button fill meets AA', () => {
    expect(contrastRatio(colors.onPrimary, colors.primaryStrong)).toBeGreaterThanOrEqual(AA);
  });

  it('contrast helpers behave', () => {
    expect(contrastRatio('#ffffff', '#000000')).toBeCloseTo(21, 0);
    expect(luminance('#000000')).toBe(0);
  });

  it('hitSlopFor grows small controls up to the minimum touch size', () => {
    expect(hitSlopFor(24, 24)).toEqual({ top: 10, bottom: 10, left: 10, right: 10 });
    expect(hitSlopFor(MIN_TOUCH, MIN_TOUCH)).toEqual({ top: 0, bottom: 0, left: 0, right: 0 });
    expect(hitSlopFor()).toEqual({ top: 22, bottom: 22, left: 22, right: 22 });
  });

  it('applyFontScaleCap keeps scaling on but capped', () => {
    applyFontScaleCap();
    expect(Text.defaultProps).toMatchObject({ allowFontScaling: true, maxFontSizeMultiplier: MAX_FONT_SCALE });
    expect(TextInput.defaultProps).toMatchObject({ maxFontSizeMultiplier: MAX_FONT_SCALE });
  });
});
