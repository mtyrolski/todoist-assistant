/** @type {import('next').NextConfig} */
module.exports = {
  output: "standalone",
  // TypeScript checking runs through npm run lint; no ESLint toolchain is used.
  eslint: { ignoreDuringBuilds: true },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_URL || "http://127.0.0.1:8000"}/api/:path*`
      }
    ];
  }
};
