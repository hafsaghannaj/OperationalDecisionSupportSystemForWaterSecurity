import type { NextConfig } from "next";

const CSP = [
  "default-src 'self'",
  // Next.js dev mode requires unsafe-eval; tighten to 'none' for prod builds
  "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  // MapLibre tiles + data URIs for map markers
  "img-src 'self' data: blob: https://server.arcgisonline.com",
  // API calls + MapLibre tile fetches
  "connect-src 'self' http://localhost:8000 https://server.arcgisonline.com https://www.geoboundaries.org",
  "font-src 'self' data:",
  // MapLibre uses Web Workers via blob URLs
  "worker-src blob:",
].join("; ");

const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Content-Security-Policy", value: CSP },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
