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
