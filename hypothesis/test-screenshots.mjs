/** Screenshots are optional test output and never default to the source tree. */
import { mkdir } from "node:fs/promises";
import path from "node:path";

export async function saveScreenshot(page, name, options = {}) {
  const directory = process.env.HYPOTHESIS_SCREENSHOT_DIR;
  if (!directory) {
    return;
  }
  await mkdir(directory, { recursive: true });
  await page.screenshot({ ...options, path: path.join(directory, name) });
}
