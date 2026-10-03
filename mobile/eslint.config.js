const js = require('@eslint/js');
const globals = require('globals');
const react = require('eslint-plugin-react');
const reactHooks = require('eslint-plugin-react-hooks');

module.exports = [
  { ignores: ['node_modules/**', 'android/**', 'ios/**', 'coverage/**', '.expo/**'] },
  js.configs.recommended,
  {
    files: ['**/*.{js,jsx}'],
    plugins: { react, 'react-hooks': reactHooks },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.es2021, ...globals.node, __DEV__: 'readonly', TextDecoder: 'readonly' },
    },
    settings: { react: { version: '18.3' } },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs['jsx-runtime'].rules,
      ...reactHooks.configs.recommended.rules,
      'react/prop-types': 'off', // plain-JS app without PropTypes (same as before)
      'no-console': 'error', // never log tokens / user data
    },
  },
  {
    files: ['**/__tests__/**/*.{js,jsx}', 'jest.*.js'],
    languageOptions: { globals: { ...globals.jest } },
  },
];
