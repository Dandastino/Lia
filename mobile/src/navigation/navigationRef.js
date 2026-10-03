import { createNavigationContainerRef } from '@react-navigation/native';

// Lets non-screen code (the 401 handler) navigate.
export const navigationRef = createNavigationContainerRef();
