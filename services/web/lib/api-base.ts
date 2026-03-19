function stripTrailingSlash(value: string): string {
  return value.replace(/\/$/, "");
}

export const CLIENT_API_PROXY_BASE = "/api/proxy";

export function resolveServerApiBaseUrl(): string {
  const rawBaseUrl =
    process.env.ODSSWS_API_BASE_URL ??
    process.env.AQUAINTEL_API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL;

  if (rawBaseUrl) {
    return stripTrailingSlash(rawBaseUrl);
  }

  if (process.env.NODE_ENV !== "production") {
    return "http://localhost:8000";
  }

  throw new Error(
    "ODSSWS_API_BASE_URL is not configured for production. " +
      "Set it in the Vercel project environment so the web app can reach the API."
  );
}

export function resolveApiBaseUrl(): string {
  if (typeof window === "undefined") {
    return resolveServerApiBaseUrl();
  }
  return CLIENT_API_PROXY_BASE;
}
