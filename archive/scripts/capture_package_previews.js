#!/usr/bin/env node

const path = require("node:path");

async function main() {
  const args = process.argv.slice(2);
  let month = "";
  let limit = 0;
  let force = false;
  const onlyBrands = [];

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === "--month") {
      month = String(args[i + 1] || "").trim();
      i += 1;
      continue;
    }
    if (arg === "--limit") {
      limit = Number(args[i + 1] || 0);
      i += 1;
      continue;
    }
    if (arg === "--brand") {
      const brand = String(args[i + 1] || "").trim();
      if (brand) {
        onlyBrands.push(brand);
      }
      i += 1;
      continue;
    }
    if (arg === "--force") {
      force = true;
    }
  }

  if (!month) {
    throw new Error("usage: node capture_package_previews.js --month YYYY-MM [--brand 品牌] [--limit N] [--force]");
  }

  const modulePath = path.join(__dirname, "package_preview_capture.mjs");
  const { captureMonthPackageScreenshots } = await import(`file://${modulePath}`);
  const result = await captureMonthPackageScreenshots({
    month,
    onlyBrands,
    limit,
    force,
  });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main().catch((error) => {
  const message = error && error.stack ? error.stack : String(error);
  process.stderr.write(`${message}\n`);
  process.exit(1);
});
