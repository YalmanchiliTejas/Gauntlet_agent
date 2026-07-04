export function getAuthCallbackUrl(): string {
  const configured = process.env.NEXT_PUBLIC_AUTH_REDIRECT_URL?.trim();
  if (configured) return configured;
  if (typeof window === "undefined") return "/auth/callback";
  return `${window.location.origin}/auth/callback`;
}
