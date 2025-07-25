import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import TicketList from './TicketList';
import { mockSuccessfulTicketsResponse, mockApiError } from '../setupTests';

// Mock data for testing
const mockTickets = [
  {
    id: 1,
    summary: 'Test Ticket 1',
    status: 'open',
    type: 'defect',
    priority: 'high',
    component: 'frontend',
    milestone: 'v1.0',
    owner: 'john@example.com',
    reporter: 'jane@example.com',
    description: 'This is a test ticket description',
    time: '2024-01-01',
    changetime: '2024-01-02'
  }
];

describe('TicketList Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    render(<TicketList />);
    
    expect(screen.getByText('Loading your tickets...')).toBeInTheDocument();
    expect(screen.getByText('🔄')).toBeInTheDocument();
  });

  it('displays user welcome message', async () => {
    mockSuccessfulTicketsResponse(mockTickets);
    render(<TicketList />);
    
    await waitFor(() => {
      expect(screen.getByText('🎫 Your Tickets')).toBeInTheDocument();
      expect(screen.getByText('Welcome back, Test!')).toBeInTheDocument();
    });
  });

  it('fetches and displays tickets successfully', async () => {
    mockSuccessfulTicketsResponse(mockTickets);
    render(<TicketList />);
    
    await waitFor(() => {
      expect(screen.getByText('Test Ticket 1')).toBeInTheDocument();
      expect(screen.getByText('Showing 1 ticket')).toBeInTheDocument();
      expect(screen.getByText('#1')).toBeInTheDocument();
    });
  });

  it('shows empty state when no tickets are returned', async () => {
    mockSuccessfulTicketsResponse([]);
    render(<TicketList />);
    
    await waitFor(() => {
      expect(screen.getByText('No tickets found')).toBeInTheDocument();
      expect(screen.getByText('📭')).toBeInTheDocument();
    });
  });

  it('handles API errors gracefully', async () => {
    mockApiError(500, 'Internal Server Error');
    render(<TicketList />);
    
    await waitFor(() => {
      expect(screen.getByText('Error loading tickets')).toBeInTheDocument();
      expect(screen.getByText('Failed to load tickets')).toBeInTheDocument();
    });
  });

  it('calls API with correct authentication headers', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ tickets: mockTickets })
    });
    global.fetch = mockFetch;
    
    render(<TicketList />);
    
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/tickets', {
        signal: expect.any(AbortSignal),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock-token'
        }
      });
    });
  });
}); 