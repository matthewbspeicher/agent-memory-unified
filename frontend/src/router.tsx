import { createBrowserRouter } from 'react-router-dom';
import { Layout } from './components/Layout';
import Dashboard from './pages/Dashboard';
import Landing from './pages/Landing';
import MemoryList from './pages/MemoryList';
import TradeHistory from './pages/TradeHistory';
import Login from './pages/Login';
import Leaderboard from './pages/Leaderboard';
import Commons from './pages/Commons';
import Arena from './pages/Arena';
import Webhooks from './pages/Webhooks';
import WorkspaceList from './pages/WorkspaceList';
import KnowledgeGraph from './pages/KnowledgeGraph';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/',
    element: <Layout />,
    children: [
      {
        index: true,
        element: <Landing />,
      },
      {
        path: 'dashboard',
        element: <Dashboard />,
      },
      {
        path: 'memories',
        element: <MemoryList />,
      },
      {
        path: 'trades',
        element: <TradeHistory />,
      },
      {
        path: 'leaderboard',
        element: <Leaderboard />,
      },
      {
        path: 'commons',
        element: <Commons />,
      },
      {
        path: 'arena',
        element: <Arena />,
      },
      {
        path: 'webhooks',
        element: <Webhooks />,
      },
      {
        path: 'workspaces',
        element: <WorkspaceList />,
      },
      {
        path: 'explorer',
        element: <KnowledgeGraph />,
      },
    ],
  },
]);
