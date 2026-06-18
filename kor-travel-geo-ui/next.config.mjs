import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vworldPackagesDir = path.join(__dirname, "node_modules", "maplibre-vworld-react", "packages");
const vworldPackagesImportPath = "./node_modules/maplibre-vworld-react/packages";

/** @type {import("next").NextConfig} */
const allowedDevOrigins = (process.env.KTG_UI_ALLOWED_DEV_ORIGINS ?? "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins,
  turbopack: {
    resolveAlias: {
      "vworld-map-core": `${vworldPackagesImportPath}/vworld-map-core/src/index.ts`,
      "vworld-map-web": `${vworldPackagesImportPath}/vworld-map-web/src/index.ts`
    }
  },
  transpilePackages: ["maplibre-vworld-react"],
  // Next 16은 dev/build 모두 Turbopack을 기본으로 쓰므로 실제 alias 해석은 위
  // `turbopack.resolveAlias`가 담당한다. 아래 webpack alias는 `--webpack` opt-out
  // 경로 전용 fallback이며 turbopack 블록과 같은 대상으로 동기 유지해야 한다.
  // (이 webpack 블록만 남고 turbopack 키가 없으면 Next 16 build가 hard-fail한다.)
  webpack(config) {
    config.resolve.alias = {
      ...(config.resolve.alias ?? {}),
      "vworld-map-core": path.join(vworldPackagesDir, "vworld-map-core", "src"),
      "vworld-map-web": path.join(vworldPackagesDir, "vworld-map-web", "src")
    };
    return config;
  }
};

export default nextConfig;
