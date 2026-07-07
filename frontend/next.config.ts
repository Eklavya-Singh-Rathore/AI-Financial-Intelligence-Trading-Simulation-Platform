import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lint runs separately in CI (typecheck + build); keep builds deterministic.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
