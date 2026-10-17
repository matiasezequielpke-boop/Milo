/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Old links land on their new homes instead of a 404.
  async redirects() {
    return [
      { source: "/chat", destination: "/", permanent: false },
      { source: "/accounts", destination: "/money", permanent: false },
    ];
  },
};

module.exports = nextConfig;
