/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Static files are copied into the backend in production. During local
  // development, dynamic app IDs must be handled by Next's dev server.
  output: process.env.NODE_ENV === "production" ? "export" : undefined,

  basePath: "/chatbot",

  images: {
    unoptimized: true
  }
};

export default nextConfig;
