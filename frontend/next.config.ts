import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // the Python engine does the work; Next.js proxies to it so the browser sees one origin
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/samples/:path*", destination: `${BACKEND}/samples/:path*` },
    ];
  },
};

export default nextConfig;
