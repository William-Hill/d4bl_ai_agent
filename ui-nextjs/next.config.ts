import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable standalone output for Docker
  output: 'standalone',
  
  // Proxy API requests to FastAPI backend
  // Note: WebSocket connections must connect directly to the backend
  // (Next.js rewrites don't support ws:// or wss:// protocols)
  // In Docker: Use API_INTERNAL_URL for server-side rewrites (internal network)
  // In browser: NEXT_PUBLIC_API_URL is used directly by the client
  async rewrites() {
    // Use internal Docker service name if available, otherwise use public URL
    const apiUrl = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
