import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { NextConfig } from "next";

// The repo-root .env is THE config file. Next only auto-loads env files from
// this directory, so pull NEXT_PUBLIC_* entries from the root file ourselves.
// Real environment variables win; a missing file is fine (Docker build args).
try {
  const rootEnv = readFileSync(join(__dirname, "..", "..", ".env"), "utf8");
  for (const line of rootEnv.split("\n")) {
    const match = /^(NEXT_PUBLIC_[A-Z0-9_]+)=(.*)$/.exec(line.trim());
    if (match && process.env[match[1]] === undefined) {
      process.env[match[1]] = match[2].replace(/^["']|["']$/g, "");
    }
  }
} catch {
  // no root .env — defaults and real env vars apply
}

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image (node server.js).
  output: "standalone",
};

export default nextConfig;
