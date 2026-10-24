/** Build synthetic library components in a temporary directory for browser tests. */
import { createRequire } from "node:module";
import { writeFile, copyFile, cp, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));

export async function buildLibraryTestFixture() {
  const destination = await mkdtemp(
    path.join(os.tmpdir(), "sidenote-library-test-"),
  );
  const previousCwd = process.cwd();
  const previousNodeEnv = process.env.NODE_ENV;
  try {
    process.chdir(path.join(root, "client"));
    process.env.NODE_ENV = "production";
    const require = createRequire(path.join(root, "client/package.json"));
    const { rollup } = require("rollup");
    const { default: configs } = await import("./client/rollup.config.js");
    const bundle = await rollup({
      ...configs[1],
      input: "dev-server/library-preview.tsx",
    });
    try {
      await bundle.write({
        dir: destination,
        format: "es",
        entryFileNames: "fixture.js",
        chunkFileNames: "[name].js",
      });
    } finally {
      await bundle.close();
    }
    await copyFile(
      path.join(root, "client/build/styles/sidebar.css"),
      path.join(destination, "sidebar.css"),
    );
    await cp(
      path.join(root, "client/src/styles/fonts"),
      path.join(destination, "fonts"),
      { recursive: true },
    );
    await writeFile(
      path.join(destination, "index.html"),
      '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>sidenote test fixture</title><link rel="stylesheet" href="sidebar.css"></head><body style="margin:0"><hypothesis-app id="app"></hypothesis-app><script type="module" src="fixture.js"></script></body></html>',
    );
    return destination;
  } catch (error) {
    await rm(destination, { recursive: true, force: true });
    throw error;
  } finally {
    process.chdir(previousCwd);
    if (previousNodeEnv === undefined) {
      delete process.env.NODE_ENV;
    } else {
      process.env.NODE_ENV = previousNodeEnv;
    }
  }
}
