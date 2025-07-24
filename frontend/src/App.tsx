import React from 'react';
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
        <h1>HobbyTrack</h1>
        <p>Modern project tracking for hobbyists</p>
        <div className="api-status">
          {apiStatus}
        </div>
      </header>
      <main>
        <TracTest />
      </main>
    </div>
  );
};

export default App; 