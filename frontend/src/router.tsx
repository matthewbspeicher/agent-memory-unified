import { createBrowserRouter } from 'react-router-dom';
import { Layout } from './components/Layout';
import Dashboard from './pages/Dashboard';
import MemoryList from './pages/MemoryList';
import TradeHistory from './pages/TradeHistory';
import Login from './pages/Login';

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
    ],
  },
]);
