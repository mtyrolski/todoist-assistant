/** @type {import('next').NextConfig} */
module.exports = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_URL || "http://127.0.0.1:8000"}/api/:path*`
      }
    ];
  }
};
