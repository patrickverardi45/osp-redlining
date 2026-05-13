import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: [
    "10.128.234.78",
    "managing-mossy-neurotic.ngrok-free.dev",
  ],
  async rewrites() {
    // `fallback` runs only when no Next.js route matched. Returning an array
    // (the prior shape) is equivalent to `afterFiles`, which fires before
    // dynamic routes like /api/jobs/[jobId]/lock-closeout and hijacks them
    // to 127.0.0.1:8000. In production Vercel has nothing on that port and
    // serves a text/plain edge 404. Fallback preserves the dev-only escape
    // hatch (where the local backend really is on 127.0.0.1:8000) without
    // shadowing dynamic API routes.
    return {
      afterFiles: [],
      fallback: [
        {
          source: "/api/:path*",
          destination: "http://127.0.0.1:8000/api/:path*",
        },
      ],
    };
  },
};

export default nextConfig;