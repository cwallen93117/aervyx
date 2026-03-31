import type { NextConfig } from "next";

const backendInternalUrl = process.env.BACKEND_INTERNAL_URL || "http://backend:8000";
const allowedDevOrigins = [
  "localhost",
  "127.0.0.1",
  "192.168.*.*",
  "10.*.*.*",
  "172.*.*.*",
  "100.*.*.*",
  ...(process.env.ALLOWED_DEV_ORIGINS?.split(",").map((origin) => origin.trim()).filter(Boolean) ?? []),
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Dockerized dev only sees container interfaces, so allow common local-network
  // ranges explicitly to keep LAN testing working across host IP changes.
  allowedDevOrigins,
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${backendInternalUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
