/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Sign-in is off for now; old links land on the chat instead of a 404.
  async redirects() {
    return [
      { source: "/chat", destination: "/", permanent: false },
      { source: "/accounts", destination: "/money", permanent: false },
      { source: "/login", destination: "/", permanent: false },
      { source: "/onboarding", destination: "/", permanent: false },
      { source: "/invite/:token*", destination: "/family", permanent: false },
    ];
  },
};

module.exports = nextConfig;
