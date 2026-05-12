import { QueryClientProvider } from '@tanstack/react-query';
import { Navigate, Outlet, createBrowserRouter } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { PageFrame } from '../components/layout/PageFrame';
import { EmptyState } from '../components/platform/EmptyState';
import { PageHeader } from '../components/platform/PageHeader';
import { AgentsPage } from '../features/agents/AgentsPage';
import { CrewsPage } from '../features/crews/CrewsPage';
import { CredentialsPage } from '../features/credentials/CredentialsPage';
import { LoginPage } from '../features/auth/LoginPage';
import { FlowsLibraryPage } from '../features/flows/FlowsLibraryPage';
import { HomePage } from '../features/home/HomePage';
import { KnowledgePage } from '../features/knowledge/KnowledgePage';
import { IOPage } from '../features/runs/IOPage';
import { RunPage } from '../features/runs/RunPage';
import { StreamingPage } from '../features/runs/StreamingPage';
import { SettingsPage } from '../features/settings/SettingsPage';
import { TasksPage } from '../features/tasks/TasksPage';
import { ToolsLibraryPage } from '../features/tools/ToolsLibraryPage';
import { useAuth } from '../hooks/useAuth';
import { queryClient } from '../lib/queryClient';
import { AuthCallbackPage } from '../features/auth/AuthCallbackPage';


function AppRouteProviders() {
  return (
    <QueryClientProvider client={queryClient}>
      <Outlet />
    </QueryClientProvider>
  );
}

function RootRedirect() {
  return <Navigate to="/login" replace />;
}

function ProtectedAppShell() {
  const { isAuthenticated } = useAuth();

  return isAuthenticated ? <AppShell /> : <Navigate to="/login" replace />;
}

function NotFoundPage() {
  return (
    <PageFrame>
      <PageHeader title="Page not found" description="The requested route is not available on the public site." />
      <EmptyState
        title="Unsupported route"
        description="Use a valid link or the login page to continue."
      />
    </PageFrame>
  );
}

export const appRoutes = [
  {
    path: '/',
    element: <AppRouteProviders />,
    children: [
      {
        index: true,
        element: <RootRedirect />,
      },
      {
        path: 'login',
        element: <LoginPage />,
      },
      {
        path: 'auth/callback',
        element: <AuthCallbackPage />,
      },
      {
        element: <ProtectedAppShell />,
        children: [
          {
            path: 'home',
            element: <HomePage />,
          },
          {
            path: 'build',
            children: [
              {
                index: true,
                element: <Navigate to="/build/agents" replace />,
              },
              {
                path: 'agents',
                element: <AgentsPage />,
              },
              {
                path: 'tasks',
                element: <TasksPage />,
              },
              {
                path: 'crews',
                element: <CrewsPage />,
              },
              {
                path: 'flows',
                element: <FlowsLibraryPage />,
              },
              {
                path: 'flows/:flowId',
                element: <FlowsLibraryPage />,
              },
              {
                path: 'tools',
                element: <ToolsLibraryPage />,
              },
              {
                path: 'credentials',
                element: <CredentialsPage />,
              },
              {
                path: 'knowledge',
                element: <KnowledgePage />,
              },
              {
                path: 'settings',
                element: <SettingsPage />,
              },
            ],
          },
          {
            path: 'run',
            children: [
              {
                index: true,
                element: <RunPage />,
              },
              {
                path: 'streaming',
                element: <StreamingPage />,
              },
              {
                path: 'io',
                element: <IOPage />,
              },
            ],
          },
        ],
      },
      {
        path: '*',
        element: <NotFoundPage />,
      },
    ],
  },
];

export const router = createBrowserRouter(appRoutes);
