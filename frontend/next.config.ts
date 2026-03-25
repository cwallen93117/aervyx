import type { NextConfig } from "next";

const backendInternalUrl = process.env.BACKEND_INTERNAL_URL || "http://backend:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["192.168.87.22", "localhost", "127.0.0.1"],
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
