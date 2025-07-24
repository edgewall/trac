import React from 'react';

interface TracTestProps {}

interface TracTestState {
  ticketIds: number[];
  loading: boolean;
  error: string | null;
}

const TracTest: React.FC<TracTestProps> = () => {
  const [state, setState] = React.useState<TracTestState>({
    ticketIds: [],
    loading: true,
    error: null
  });

  React.useEffect(() => {
    const fetchTracData = async (): Promise<void> => {
      try {
        setState(prev => ({ ...prev, loading: true, error: null }));
        
        // Create AbortController for request timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
        
        const response = await fetch('/api/test-trac', {
          signal: controller.signal,
          headers: {
            'Content-Type': 'application/json',
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
        
        if (data.status !== 'success') {
          throw new Error(`API returned error status: ${data.status || 'unknown'}`);
        }
        
        if (!Array.isArray(data.sample_ticket_ids)) {
          throw new Error('Invalid response: Missing or invalid sample_ticket_ids array');
        }
        
        // Success - update state with ticket IDs
        setState(prev => ({
          ...prev,
          ticketIds: data.sample_ticket_ids,
          loading: false,
          error: null
        }));
        
        console.log('API Response:', data);
        console.log('Updated state will be:', {
          ticketIds: data.sample_ticket_ids,
          loading: false,
          error: null
        });
        
      } catch (error) {
        console.error('API call failed:', error);
        
        let errorMessage = 'Failed to load ticket data';
        
        if (error instanceof Error) {
          if (error.name === 'AbortError') {
            errorMessage = 'Request timed out - please try again';
          } else if (error.message.includes('Failed to fetch')) {
            errorMessage = 'Network error - check your connection and try again';
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

    fetchTracData();
  }, []);

  console.log('TracTest render - current state:', state);
  console.log('TracTest render - conditions:', {
    loading: state.loading,
    error: state.error,
    ticketIdsLength: state.ticketIds.length,
    showSuccess: !state.loading && !state.error && state.ticketIds.length > 0
  });

  return (
    <div className="trac-test" style={{ border: '2px solid blue', padding: '20px', margin: '20px' }}>
      <h2>Trac Test Component</h2>
      <div className="trac-test-content">
        {state.loading && (
          <div className="loading">
            <p>🔄 Loading ticket data from Trac...</p>
          </div>
        )}
        
        {state.error && (
          <div className="error" style={{ color: 'red', padding: '10px', border: '1px solid red', borderRadius: '4px', backgroundColor: '#fee' }}>
            <p>❌ Error: {state.error}</p>
            <button 
              onClick={() => window.location.reload()} 
              style={{ 
                marginTop: '8px', 
                padding: '6px 12px', 
                backgroundColor: '#dc3545', 
                color: 'white', 
                border: 'none', 
                borderRadius: '4px', 
                cursor: 'pointer' 
              }}
            >
              🔄 Try Again
            </button>
          </div>
        )}
        
        {!state.loading && !state.error && state.ticketIds.length > 0 && (
          <div className="ticket-list">
            <h3>📋 Ticket IDs from Trac Database:</h3>
            <ul style={{ listStyle: 'none', padding: 0 }}>
              {state.ticketIds.map((ticketId) => (
                <li 
                  key={ticketId} 
                  style={{ 
                    padding: '8px 12px', 
                    margin: '4px 0', 
                    backgroundColor: '#f0f0f0', 
                    borderRadius: '4px',
                    border: '1px solid #ddd'
                  }}
                >
                  🎫 Ticket ID: <strong>{ticketId}</strong>
                </li>
              ))}
            </ul>
            <p style={{ marginTop: '16px', fontSize: '14px', color: '#666' }}>
              ✅ Successfully retrieved {state.ticketIds.length} ticket IDs from legacy Trac database!
            </p>
          </div>
        )}
        
        {!state.loading && !state.error && state.ticketIds.length === 0 && (
          <div className="no-data">
            <p>📭 No ticket IDs found in the database.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default TracTest; 