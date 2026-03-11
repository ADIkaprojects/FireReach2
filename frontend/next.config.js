/** @type {import('next').NextConfig} */
const nextConfig = {
  // Proxy API calls in dev so the frontend and backend can run on different ports
  async rewrites() {
    return process.env.NODE_ENV === 'development'
      ? [
          {
            source: '/api/:path*',
            destination: `${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/:path*`,
          },
        ]
      : [];
  },
};

module.exports = nextConfig;
