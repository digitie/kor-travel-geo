/** @type {import("next").NextConfig} */
const allowedDevOrigins = (process.env.KRADDR_GEO_UI_ALLOWED_DEV_ORIGINS ?? "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins
};

export default nextConfig;
