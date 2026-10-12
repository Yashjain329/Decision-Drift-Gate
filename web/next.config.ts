import type { NextConfig } from 'next';

// Static export: `next build` writes plain files to web/out, which `ddg serve` serves.
// No Node at runtime; the engine's same-origin and session-token checks stay authoritative.
const config: NextConfig = {
  output: 'export',
  images: { unoptimized: true },
  reactStrictMode: true,
  poweredByHeader: false,
};

export default config;
