import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Smaller production image for Render starter RAM (ADR 0004 / M3.5b).
  output: "standalone",
  // Monorepo: include files outside apps/web in the file trace.
  outputFileTracingRoot: path.join(__dirname, "../.."),
};

export default nextConfig;
