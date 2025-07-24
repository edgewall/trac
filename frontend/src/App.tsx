import React from 'react';
import {
  SignedIn,
  SignedOut,
  SignInButton,
  SignUpButton,
  UserButton,
} from '@clerk/clerk-react';
import './App.css';
import TracTest from './components/TracTest';

interface AppProps {}

const App: React.FC<AppProps> = () => {
  const [apiStatus, setApiStatus] = React.useState<string>('Loading...');

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

  return (
    <div className="App">
      <header className="App-header">
        <h1>🎯 HobbyTrack</h1>
        <p>Modern project tracking for hobbyists</p>
        
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
            <h2>Welcome to your project dashboard!</h2>
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