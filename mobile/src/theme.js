// Single source of truth for colours, spacing and sizes. Every text/background
// pair below meets WCAG AA (4.5:1 for normal text); src/__tests__/theme.test.js
// recomputes the ratios so a future edit cannot silently break contrast.

export const colors = {
  background: '#0f0f1a',
  surface: '#1a1a2e',
  surfaceRaised: '#2a2a4a',
  border: '#3a3a5e',
  borderSubtle: '#1e1e3a',
  panel: '#12121f',
  micOnBg: '#1a2a3a',
  micOffBg: '#2a1a1a',

  text: '#ffffff',
  textSecondary: '#c4c4d8',
  textMuted: '#9a9ab8', // was #666/#888: too faint on the dark surfaces
  placeholder: '#8a8aa8',

  primary: '#667eea', // accent text / links on dark backgrounds
  primaryStrong: '#4f5fd6', // button fill: white text on it reaches > 5:1
  onPrimary: '#ffffff',

  danger: '#f87171',
  dangerBg: 'rgba(239, 68, 68, 0.12)',
  dangerBorder: 'rgba(239, 68, 68, 0.45)',

  success: '#34d399',
  successBg: 'rgba(34, 197, 94, 0.12)',
  successBorder: 'rgba(34, 197, 94, 0.45)',

  warning: '#fbbf24',
  overlay: 'rgba(0, 0, 0, 0.7)',
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };

export const radius = { sm: 8, md: 10, lg: 16, pill: 22 };

// Minimum touch target (Apple HIG 44pt, Material 48dp rounded down).
export const MIN_TOUCH = 44;

// hitSlop that grows a small control to at least MIN_TOUCH in each direction.
export function hitSlopFor(width = 0, height = 0) {
  const x = Math.max(0, Math.ceil((MIN_TOUCH - width) / 2));
  const y = Math.max(0, Math.ceil((MIN_TOUCH - height) / 2));
  return { top: y, bottom: y, left: x, right: x };
}

// Dynamic type: allow system font scaling but cap it so layouts do not break.
export const MAX_FONT_SCALE = 1.6;

// WCAG relative luminance / contrast helpers (used by tests).
function channel(v) {
  const s = v / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex) {
  const h = hex.replace('#', '');
  const n = parseInt(h, 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(foreground, background) {
  const a = luminance(foreground);
  const b = luminance(background);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}
