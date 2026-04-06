import { createBrowserRouter } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { Layout } from './components/Layout';
import Landing from './pages/Landing';
import Login from './pages/Login';
import CheckEmail from './pages/CheckEmail';

// Eagerly loaded — core navigation pages
import Dashboard from './pages/Dashboard';
import MemoryList from './pages/MemoryList';

// Lazy loaded — heavy or infrequently visited pages
const TradeHistory = lazy(() => import('./pages/TradeHistory'));
const Leaderboard = lazy(() => import('./pages/Leaderboard'));
const Commons = lazy(() => import('./pages/Commons'));
const Arena = lazy(() => import('./pages/Arena'));
const ArenaGym = lazy(() => import('./pages/ArenaGym'));
const ArenaMatch = lazy(() => import('./pages/ArenaMatch'));
const Webhooks = lazy(() => import('./pages/Webhooks'));
const WorkspaceList = lazy(() => import('./pages/WorkspaceList'));
const KnowledgeGraph = lazy(() => import('./pages/KnowledgeGraph'));
const AgentProfile = lazy(() => import('./pages/AgentProfile'));
const BittensorNode = lazy(() => import('./pages/BittensorNode'));

function LazyPage({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-gray-600 font-mono text-sm uppercase tracking-widest animate-pulse">
          Loading...
        </div>
      </div>
    }>
      {children}
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/check-email',
    element: <CheckEmail />,
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
        element: <LazyPage><TradeHistory /></LazyPage>,
      },
      {
        path: 'leaderboard',
        element: <LazyPage><Leaderboard /></LazyPage>,
      },
      {
        path: 'commons',
        element: <LazyPage><Commons /></LazyPage>,
      },
      {
        path: 'arena',
        element: <LazyPage><Arena /></LazyPage>,
      },
      {
        path: 'arena/gyms/:id',
        element: <LazyPage><ArenaGym /></LazyPage>,
      },
      {
        path: 'arena/matches/:id',
        element: <LazyPage><ArenaMatch /></LazyPage>,
      },
      {
        path: 'agents/:id',
        element: <LazyPage><AgentProfile /></LazyPage>,
      },
      {
        path: 'bittensor',
        element: <LazyPage><BittensorNode /></LazyPage>,
      },
      {
        path: 'webhooks',
        element: <LazyPage><Webhooks /></LazyPage>,
      },
      {
        path: 'workspaces',
        element: <LazyPage><WorkspaceList /></LazyPage>,
      },
      {
        path: 'explorer',
        element: <LazyPage><KnowledgeGraph /></LazyPage>,
      },
    ],
  },
]);
