import axios from 'axios';
import { storage } from './storage';

const API_URL = (process.env.EXPO_PUBLIC_API_URL).replace(/\/+$/, '');

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(async (config) => {
  const token = await storage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error?.response?.status === 401) {
      await storage.removeItem('token');
      await storage.removeItem('user');
    }
    return Promise.reject(error);
  },
);
