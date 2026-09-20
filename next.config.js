const { execFileSync } = require('node:child_process');
let buildCommit = process.env.BUILD_COMMIT || 'unknown';
try { buildCommit = execFileSync('git', ['rev-parse', '--short', 'HEAD'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim(); } catch { /* Source archives may have no .git. */ }

/** @type {import('next').NextConfig} */
const nextConfig = {
  env: { NEXT_PUBLIC_BUILD_COMMIT: buildCommit },
  experimental: {
    typedRoutes: false,
  },
};

module.exports = nextConfig;
