/** @type {import('next').NextConfig} */
const internalApiUrl = (process.env.FORGE3D_INTERNAL_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/forge3d-api/:path*",
        destination: `${internalApiUrl}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
