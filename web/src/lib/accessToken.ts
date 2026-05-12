// In-memory access token store. Never persisted to localStorage.
// Cleared on page unload naturally; re-populated by authClient.refresh() on boot.

let _token: string | null = null;

export function getAccessToken(): string | null {
  return _token;
}

export function setAccessToken(token: string): void {
  _token = token;
}

export function clearAccessToken(): void {
  _token = null;
}
