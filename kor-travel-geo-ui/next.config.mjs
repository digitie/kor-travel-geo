const allowedDevOrigins = (process.env.KTG_UI_ALLOWED_DEV_ORIGINS ?? "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

/** @type {import("next").NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins,
  // CPU2·2GiB 빌드에서 host CPU 수로 worker가 과다 생성되는 것을 막는다.
  experimental: { cpus: 2 },
  // GitHub 소스에서 빌드한 공개 배포물의 진입점을 그대로 사용한다.
  transpilePackages: ["vworld-map-core", "vworld-map-web"]
};

export default nextConfig;
