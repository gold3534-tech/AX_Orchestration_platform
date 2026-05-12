import { useSyncExternalStore } from 'react';

const AUTH_TOKEN_STORAGE_KEY = 'ai-oh.auth-token';
const listeners = new Set<() => void>();

function emitChange() {
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);

  function handleStorageEvent(event: StorageEvent) {
    if (event.key === AUTH_TOKEN_STORAGE_KEY || event.key === null) {
      listener();
    }
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('storage', handleStorageEvent);
  }

  return () => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('storage', handleStorageEvent);
    }
    listeners.delete(listener);
  };
}

export function getStoredAccessToken() {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredAccessToken(accessToken: string | null) {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    if (accessToken) {
      window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, accessToken);
    } else {
      window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    }
  } catch {
    return;
  }

  emitChange();
}

export function useAuth() {
  const accessToken = useSyncExternalStore(subscribe, getStoredAccessToken, () => null);

  return {
    accessToken,
    isAuthenticated: Boolean(accessToken),
    clearAccessToken: () => setStoredAccessToken(null),
    setAccessToken: setStoredAccessToken,
  };
}
