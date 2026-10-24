/** Render the original sidenote vector into Chrome's required icon sizes. */
import { readFile, writeFile } from "node:fs/promises";
import { chromium } from "../hypothesis/client/node_modules/playwright/index.mjs";

const root = new URL("../", import.meta.url);
const source = await readFile(new URL("assets/sidenote.svg", root), "utf8");
const images = new URL("hypothesis/browser-extension/src/images/", root);
await writeFile(new URL("sidenote.svg", images), source);
const icons = [
  ["sidenote16.png", 16, "#48658a"],
  ["sidenote48.png", 48, "#48658a"],
  ["sidenote128.png", 128, "#48658a"],
  ["sidenote-active.png", 19, "#48658a"],
  ["sidenote-active@2x.png", 38, "#48658a"],
  ["sidenote-inactive.png", 19, "#78828d"],
  ["sidenote-inactive@2x.png", 38, "#78828d"],
];
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  for (const [name, size, color] of icons) {
    await page.setViewportSize({ width: size, height: size });
    await page.setContent(
      `<style>body{margin:0}svg{display:block;width:100vw;height:100vh}</style>${source.replace("#48658a", color)}`,
    );
    await page.screenshot({
      path: new URL(name, images).pathname,
      omitBackground: true,
    });
  }
} finally {
  await browser.close();
}
console.log(
  "Rendered sidenote SVG and seven Chrome icon variants. Export the patches and rebuild.",
);
