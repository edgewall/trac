import React from 'react';
import { useAuth, useUser } from '@clerk/clerk-react';

interface Ticket {
  id: number;
  summary: string;
  status: string;
  type: string;
  priority: string;
  component: string;
  milestone: string;
  owner: string;
  reporter: string;
  description: string;
  time: string;
  changetime: string;
}

interface TicketListProps {}

interface TicketListState {
  tickets: Ticket[];
  loading: boolean;
  error: string | null;
}

const TicketList: React.FC<TicketListProps> = () => {
  const { isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  
  const [state, setState] = React.useState<TicketListState>({
    tickets: [],
    loading: true,
    error: null
  });

  React.useEffect(() => {
    const fetchTickets = async (): Promise<void> => {
      // Only fetch if user is signed in
      if (!isSignedIn) {
        setState(prev => ({
          ...prev,
          loading: false,
          error: 'Please sign in to view tickets'
        }));
        return;
      }

      try {
        setState(prev => ({ ...prev, loading: true, error: null }));
        
        // Get authentication token from Clerk
        const token = await getToken();
        
        // Create AbortController for request timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
        
        const response = await fetch('/api/tickets', {
          signal: controller.signal,
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          }
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
          let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
          
          // Try to get error details from response
          try {
            const errorData = await response.json();
            if (errorData.detail) {
              errorMessage = `${errorMessage} - ${errorData.detail}`;
            }
          } catch {
            // If we can't parse error response, use status text
          }
          
          throw new Error(errorMessage);
        }
        
        const data = await response.json();
        
        // Validate response structure
        if (!data || typeof data !== 'object') {
          throw new Error('Invalid response: Expected JSON object');
        }
        
        if (!Array.isArray(data.tickets)) {
          throw new Error('Invalid response: Missing or invalid tickets array');
        }
        
        // Success - update state with tickets
        setState(prev => ({
          ...prev,
          tickets: data.tickets,
          loading: false,
          error: null
        }));
        
        console.log('Tickets loaded successfully:', data.tickets);
        
      } catch (error) {
        console.error('Failed to fetch tickets:', error);
        
        let errorMessage = 'Failed to load tickets';
        
        if (error instanceof Error) {
          if (error.name === 'AbortError') {
            errorMessage = 'Request timed out - please try again';
          } else if (error.message.includes('Failed to fetch')) {
            errorMessage = 'Network error - check your connection and try again';
          } else if (error.message.includes('401')) {
            errorMessage = 'Authentication error - please sign in again';
          } else {
            errorMessage = error.message;
          }
        }
        
        setState(prev => ({
          ...prev,
          loading: false,
          error: errorMessage
        }));
      }
    };

    fetchTickets();
  }, [isSignedIn, getToken]); // Re-fetch when authentication state changes

  // Don't render anything if user is not signed in
  if (!isSignedIn) {
    return null;
  }

  return (
    <div className="ticket-list" style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <div className="ticket-list-header" style={{ marginBottom: '20px' }}>
        <h2>🎫 Your Tickets</h2>
        {user && (
          <p style={{ color: '#666', fontSize: '14px' }}>
            Welcome back, {user.firstName || user.primaryEmailAddress?.emailAddress || 'User'}!
          </p>
        )}
      </div>
      
      <div className="ticket-list-content">
        {state.loading && (
          <div className="loading" style={{ textAlign: 'center', padding: '40px' }}>
            <div style={{ fontSize: '24px', marginBottom: '10px' }}>🔄</div>
            <p>Loading your tickets...</p>
          </div>
        )}
        
        {state.error && (
          <div 
            className="error" 
            style={{ 
              color: '#dc3545', 
              padding: '20px', 
              border: '1px solid #dc3545', 
              borderRadius: '8px', 
              backgroundColor: '#f8d7da',
              marginBottom: '20px'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '18px' }}>❌</span>
              <div>
                <strong>Error loading tickets</strong>
                <p style={{ margin: '5px 0 0 0', fontSize: '14px' }}>{state.error}</p>
              </div>
            </div>
            <button 
              onClick={() => window.location.reload()} 
              style={{ 
                marginTop: '15px', 
                padding: '8px 16px', 
                backgroundColor: '#dc3545', 
                color: 'white', 
                border: 'none', 
                borderRadius: '4px', 
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              🔄 Try Again
            </button>
          </div>
        )}
        
        {!state.loading && !state.error && state.tickets.length > 0 && (
          <div className="tickets-grid">
            <div style={{ marginBottom: '15px', color: '#666', fontSize: '14px' }}>
              Showing {state.tickets.length} ticket{state.tickets.length !== 1 ? 's' : ''}
            </div>
            
            <div style={{ 
              display: 'grid', 
              gap: '16px',
              gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))'
            }}>
              {state.tickets.map((ticket) => (
                <div 
                  key={ticket.id} 
                  className="ticket-card"
                  style={{ 
                    padding: '20px', 
                    border: '1px solid #e0e0e0', 
                    borderRadius: '8px',
                    backgroundColor: '#fafafa',
                    boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
                    transition: 'box-shadow 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.boxShadow = '0 4px 8px rgba(0,0,0,0.1)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.boxShadow = '0 2px 4px rgba(0,0,0,0.05)';
                  }}
                >
                  <div className="ticket-header" style={{ marginBottom: '12px' }}>
                    <h3 style={{ 
                      margin: '0 0 8px 0', 
                      fontSize: '16px', 
                      color: '#2c3e50',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px'
                    }}>
                      <span style={{ 
                        backgroundColor: '#007bff', 
                        color: 'white', 
                        padding: '2px 8px', 
                        borderRadius: '4px',
                        fontSize: '12px',
                        fontWeight: 'bold'
                      }}>
                        #{ticket.id}
                      </span>
                      {ticket.summary}
                    </h3>
                  </div>
                  
                  <div className="ticket-meta" style={{ marginBottom: '12px' }}>
                    <div style={{ 
                      display: 'grid', 
                      gridTemplateColumns: '1fr 1fr', 
                      gap: '8px',
                      fontSize: '13px'
                    }}>
                      <div>
                        <strong>Status:</strong> 
                        <span style={{ 
                          marginLeft: '5px',
                          padding: '2px 6px',
                          borderRadius: '3px',
                          backgroundColor: ticket.status === 'closed' ? '#28a745' : 
                                        ticket.status === 'assigned' ? '#ffc107' : '#6c757d',
                          color: 'white',
                          fontSize: '11px'
                        }}>
                          {ticket.status}
                        </span>
                      </div>
                      <div><strong>Type:</strong> {ticket.type}</div>
                      <div><strong>Priority:</strong> {ticket.priority}</div>
                      <div><strong>Component:</strong> {ticket.component}</div>
                    </div>
                  </div>
                  
                  {ticket.description && (
                    <div className="ticket-description" style={{ marginBottom: '12px' }}>
                      <p style={{ 
                        margin: 0, 
                        fontSize: '13px', 
                        color: '#555',
                        lineHeight: '1.4',
                        maxHeight: '60px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        display: '-webkit-box',
                        WebkitLineClamp: 3,
                        WebkitBoxOrient: 'vertical'
                      }}>
                        {ticket.description}
                      </p>
                    </div>
                  )}
                  
                  <div className="ticket-footer" style={{ 
                    fontSize: '12px', 
                    color: '#888',
                    borderTop: '1px solid #e0e0e0',
                    paddingTop: '10px'
                  }}>
                    <div>Owner: {ticket.owner || 'Unassigned'}</div>
                    <div>Reporter: {ticket.reporter}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        
        {!state.loading && !state.error && state.tickets.length === 0 && (
          <div className="no-tickets" style={{ 
            textAlign: 'center', 
            padding: '60px 20px',
            color: '#666'
          }}>
            <div style={{ fontSize: '48px', marginBottom: '20px' }}>📭</div>
            <h3 style={{ margin: '0 0 10px 0', color: '#555' }}>No tickets found</h3>
            <p style={{ margin: 0, fontSize: '14px' }}>
              You don't have any tickets yet. Create your first ticket to get started!
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default TicketList; 