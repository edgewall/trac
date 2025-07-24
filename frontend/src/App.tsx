import React from 'react';
import {
  SignedIn,
  SignedOut,
  SignInButton,
  SignUpButton,
  UserButton,
  useAuth,
  useUser,
} from '@clerk/clerk-react';
import './App.css';
import TracTest from './components/TracTest';

interface AppProps {}

const App: React.FC<AppProps> = () => {
  const [apiStatus, setApiStatus] = React.useState<string>('Loading...');
  
  // Utilize Clerk's authentication hooks for programmatic access to auth state
  const { isSignedIn, isLoaded } = useAuth();
  const { user } = useUser();

  React.useEffect(() => {
    const testApi = async (): Promise<void> => {
      try {
        const response = await fetch('/api/health');
        const data = await response.json();
        setApiStatus(`API Status: ${data.status}`);
      } catch (error) {
        setApiStatus('API connection failed');
        console.error('API test failed:', error);
      }
    };

    testApi();
  }, []);

  // Show loading state while Clerk loads
  if (!isLoaded) {
    return (
      <div className="App">
        <header className="App-header">
          <h1>🎯 HobbyTrack</h1>
          <p>Loading authentication...</p>
        </header>
      </div>
    );
  }

  return (
    <div className="App">
      <header className="App-header">
        <h1>🎯 HobbyTrack</h1>
        <p>Modern project tracking for hobbyists</p>
        
        {/* Debug info showing hook values */}
        <div className="auth-debug" style={{ fontSize: '12px', opacity: 0.7, marginBottom: '10px' }}>
          Auth Status: {isSignedIn ? 'Signed In' : 'Signed Out'} | 
          User: {user?.firstName || 'None'} | 
          Loaded: {isLoaded ? 'Yes' : 'No'}
        </div>
        
        <SignedOut>
          <div className="auth-section">
            <h2>Welcome! Please sign in to continue</h2>
            <div className="auth-buttons">
              <SignInButton mode="modal">
                <button className="auth-button signin">Sign In</button>
              </SignInButton>
              <SignUpButton mode="modal">
                <button className="auth-button signup">Sign Up</button>
              </SignUpButton>
            </div>
          </div>
        </SignedOut>
        
        <SignedIn>
          <div className="user-section">
            <UserButton afterSignOutUrl="/" />
            <h2>Welcome back{user?.firstName ? `, ${user.firstName}` : ''}!</h2>
            <p>Email: {user?.primaryEmailAddress?.emailAddress}</p>
          </div>
          <div className="api-status">
            {apiStatus}
          </div>
        </SignedIn>
      </header>
      
      <main>
        <SignedIn>
          <TracTest />
        </SignedIn>
      </main>
    </div>
  );
};

export default App; 