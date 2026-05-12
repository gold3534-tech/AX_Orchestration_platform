import { type ReactNode } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { queryClient } from '../lib/queryClient';

type AppRootProps = {
  children?: ReactNode;
};

export default function AppRoot({ children }: AppRootProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <App />
      {children}
    </QueryClientProvider>
  );
}
