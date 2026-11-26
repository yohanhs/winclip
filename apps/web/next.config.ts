import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@winclip/api-client"],
  // El monorepo usa pnpm en la raíz; evita que Next infiera otro workspace root.
  outputFileTracingRoot: path.resolve(process.cwd(), "../.."),
};

export default nextConfig;
