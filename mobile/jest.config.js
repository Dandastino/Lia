module.exports = {
  preset: 'jest-expo',
  // The first test of a file pays the Babel/Metro transform cost; a cold cache (CI) exceeds the 5 s default.
  testTimeout: 60000,
  setupFiles: ['<rootDir>/jest.setup.js'],
  // Fake timers keep TouchableOpacity press animations (and auto-dismiss timers) deterministic.
  fakeTimers: { enableGlobally: true },
  setupFilesAfterEnv: ['<rootDir>/jest.setup.after.js'],
  testMatch: ['<rootDir>/src/**/__tests__/**/*.test.{js,jsx}'],
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@livekit/.*|livekit-client))',
  ],
  collectCoverageFrom: [
    'src/**/*.{js,jsx}',
    '!src/**/*.styles.js',
    '!src/**/__tests__/**',
  ],
  coverageReporters: ['text-summary', 'text', 'lcov'],
  coverageThreshold: {
    global: { statements: 90, branches: 80, functions: 85, lines: 90 },
  },
};
