import '@testing-library/jest-dom';
import React from 'react';
import { vi, afterEach } from 'vitest';

// Global mock for Clerk
vi.mock('@clerk/clerk-react', () => ({
  useAuth: () => ({
    isSignedIn: true,
    getToken: vi.fn(() => Promise.resolve('mock-token')),
    isLoaded: true
  }),
  useUser: () => ({
    user: {
      firstName: 'Test',
      lastName: 'User',
      primaryEmailAddress: {
        emailAddress: 'test@example.com'
      }
    },
    isLoaded: true
  }),
  SignedIn: ({ children }: { children: React.ReactNode }) => children,
  SignedOut: ({ children }: { children: React.ReactNode }) => null,
  SignInButton: ({ children }: { children: React.ReactNode }) => children,
  SignUpButton: ({ children }: { children: React.ReactNode }) => children,
  UserButton: () => React.createElement('div', { 'data-testid': 'user-button' }, 'User Button')
}));

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Helper function to mock successful API responses
export const mockSuccessfulTicketsResponse = (tickets: any[] = []) => {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve({ tickets })
  });
};

// Helper function to mock API errors
export const mockApiError = (status = 500, message = 'Server Error') => {
  mockFetch.mockRejectedValueOnce(new Error(`HTTP ${status}: ${message}`));
};

// Reset all mocks after each test
afterEach(() => {
  vi.clearAllMocks();
}); 