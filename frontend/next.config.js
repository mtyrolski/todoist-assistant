/** @type {import('next').NextConfig} */
const androidExport = process.env.TODOIST_ANDROID_EXPORT === "1";
module.exports = {
  output: androidExport ? "export" : "standalone",
  distDir: process.env.TODOIST_NEXT_DIST_DIR || ".next",
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
if (androidExport) delete module.exports.rewrites;
