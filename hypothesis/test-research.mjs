import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { chromium } from './client/node_modules/playwright/index.mjs';
import { saveScreenshot } from './test-screenshots.mjs';

const root = path.dirname(new URL(import.meta.url).pathname);
const config = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
const cache = path.join(os.homedir(), 'Library/Caches/ms-playwright');
let executablePath = process.env.HYPOTHESIS_CHROMIUM_PATH;
if (!executablePath && process.platform === 'darwin') {
  for (const name of (await fs.readdir(cache).catch(() => [])).filter(n => /^chromium-\d+$/.test(n)).sort().reverse()) {
    const candidate = path.join(cache, name, 'chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing');
    try { await fs.access(candidate); executablePath = candidate; break; } catch {}
  }
}
const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'research-test-browser-'));
const extension = path.join(root, 'browser-extension/build');
const context = await chromium.launchPersistentContext(profile, {
  executablePath, headless: true, viewport: { width: 1440, height: 1000 },
  ignoreDefaultArgs: ['--disable-extensions'],
  args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
});
try {
  const worker = context.serviceWorkers()[0] ?? await context.waitForEvent('serviceworker');
  const id = new URL(worker.url()).host;
  // Same isolated test transport as test-native.mjs; the user's bridge is never used.
  await worker.evaluate(async ({ port, key }) => {
    await chrome.storage.local.set({ researchKey: key });
    const fetchReal = globalThis.fetch.bind(globalThis);
    globalThis.fetch = (url, options) => fetchReal(String(url).replace('http://127.0.0.1:8765', `http://127.0.0.1:${port}`), options);
  }, config);
  const page = await context.newPage();
  await page.goto(`chrome-extension://${id}/client/notebook.html?local-library=1&tab=research`);
  await page.getByRole('button', { name: 'Find in library', exact: true }).click();
  assert.equal(new URL(page.url()).hash, '#/research/find');
  await page.getByRole('checkbox', { name: 'Find related terms with AI' }).uncheck();
  await page.getByRole('combobox', { name: 'Result type' }).selectOption('annotations');
  await page.getByRole('textbox', { name: 'Question or search' }).fill('give me all annotations related to computational social science');
  await page.getByRole('button', { name: 'Search library', exact: true }).click();
  await page.getByRole('heading', { name: '2 matching annotations', exact: true }).waitFor();
  assert.equal(await page.locator('.rw-evidence a[href^="https://hypothes.is/a/"]').count(), 2);
  await page.evaluate(() => { location.hash = '#/research/wiki'; });
  await page.getByRole('button', { name: 'Enable developer mode', exact: true }).click();
  assert.equal(new URL(page.url()).hash, '#/research/wiki');
  await page.goBack();
  await page.getByRole('heading', { name: '2 matching annotations', exact: true }).waitFor();
  assert.equal(new URL(page.url()).hash, '#/research/find');
  await page.goForward();
  await page.getByRole('button', { name: 'Build wiki from library', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Build wiki from library', exact: true }).click();
  await page.getByRole('button', { name: 'Update wiki from library', exact: true }).waitFor();
  await page.locator('nav[aria-label="Wiki pages"] button').filter({ hasText: 'computational social science' }).click();
  await page.getByRole('button', { name: 'Synthesize this topic', exact: true }).click();
  await page.getByText('Synthetic synthesis fixture: network structure affects diffusion.', { exact: false }).waitFor();
  await page.getByRole('button', { name: 'Check wiki', exact: true }).click();
  await page.getByText('Wiki checks passed:', { exact: false }).waitFor();
  await saveScreenshot(page, 'research-wiki-preview.png', { fullPage: true });
  for (const name of ['Overview', 'Key ideas', 'Disagreements', 'Open questions']) {
    await page.getByRole('heading', { name, exact: true }).waitFor();
  }
  await page.locator('.rw-citations summary').first().click();
  await page.locator('.rw-citations blockquote').first().waitFor({ state: 'visible' });
  await page.getByRole('button', { name: 'Explore connections', exact: true }).click();
  assert.match(new URL(page.url()).hash, /^#\/research\/graph\/topic-/);
  await page.getByRole('img', { name: /Knowledge graph with [1-9]\d* nodes/ }).waitFor();
  assert.equal(await page.locator('.rw-graph canvas').count() > 0, true);
  await page.locator('.rw-connection-list button').filter({ hasText: 'studies' }).click();
  const inspector = page.getByRole('complementary', { name: 'Connection inspector', exact: true });
  await inspector.getByText('Synthetic connection fixture:', { exact: false }).waitFor();
  await inspector.locator('.rw-citations summary').click();
  await inspector.locator('blockquote').first().waitFor();
  await inspector.getByText('An invented reader comment.', { exact: false }).waitFor();
  await saveScreenshot(page, 'research-graph-preview.png', { fullPage: true });
  await page.getByRole('button', { name: 'Switch to dark mode', exact: true }).click();
  assert.equal(await page.locator('.ld-app').getAttribute('data-color-scheme'), 'dark');
  await inspector.locator('blockquote').first().waitFor({ state: 'visible' });
  await saveScreenshot(page, 'research-graph-dark.png', { fullPage: true });
  await page.getByRole('button', { name: 'Switch to light mode', exact: true }).click();
  await inspector.getByRole('button', { name: 'Explore first concept', exact: true }).click();
  await inspector.getByRole('heading', { name: 'computational social science', exact: true }).waitFor();
  assert.equal(await inspector.getByText('Synthetic connection fixture:', { exact: false }).count(), 0);
  await page.locator('.rw-connection-list button').filter({ hasText: 'studies' }).click();
  await page.getByRole('button', { name: 'Expand neighborhood', exact: true }).click();
  await inspector.getByText('Synthetic connection fixture:', { exact: false }).waitFor();
  await inspector.getByRole('button', { name: 'Explore second concept', exact: true }).click();
  assert.match(new URL(page.url()).hash, /^#\/research\/graph\/concept-/);
  await page.reload();
  await inspector.getByRole('heading', { name: 'Information diffusion', exact: true }).waitFor();
  await inspector.getByRole('button', { name: 'Read wiki page', exact: true }).click();
  await page.getByRole('heading', { name: 'Information diffusion', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Topic classification', exact: true }).click();
  assert.equal(new URL(page.url()).hash, '#/research/kura/hierarchy');
  await page.getByRole('button', { name: 'Classify all notes', exact: true }).click();
  await page.locator('.kura-tree-topic').first().waitFor();
  assert.equal(await page.locator('.kura-tree-topic:visible').count(), 5);
  await saveScreenshot(page, 'research-topics-preview.png', { fullPage: true });
  await page.goto(`${page.url()}/clusters/repeated-0`);
  await page.getByRole('complementary', { name: 'Cluster evidence', exact: true })
    .getByRole('heading', { name: 'Synthetic subject 1', exact: true }).waitFor();
  await page.reload();
  await page.getByRole('complementary', { name: 'Cluster evidence', exact: true })
    .getByRole('heading', { name: 'Synthetic subject 1', exact: true }).waitFor();
  assert.equal(await page.locator('.kura-tree-topic:visible').count(), 5);
  assert.equal(await page.locator('.kura-tree-topic[aria-pressed="true"]').count(), 1);
  await page.locator('.kura-tree-toggle').first().click();
  assert.equal(await page.locator('.kura-tree-topic:visible').count(), 1);
  await page.locator('.kura-tree-toggle').first().press('Enter');
  assert.equal(await page.locator('.kura-tree-topic:visible').count(), 5);
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  await page.getByRole('group', { name: 'Kura cluster map', exact: true }).waitFor();
  assert.equal(await page.locator('.kura-bubble').count(), 4);
  await page.locator('.kura-bubble').first().press('Enter');
  await page.getByText('Synthetic evidence summary.', { exact: true }).waitFor();
  await page.getByText('Read original evidence', { exact: true }).click();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.getByRole('button', { name: 'Reset map', exact: true }).click();
  await saveScreenshot(page, 'research-kura-preview.png', { fullPage: true });
  await page.getByRole('button', { name: 'Hierarchy', exact: true }).click();
  assert.match(new URL(page.url()).hash, /^#\/research\/kura\/hierarchy/);
  assert.equal(await page.locator('.kura-tree-topic').count(), 5);
  await page.getByRole('button', { name: 'Topic sizes', exact: true }).click();
  assert.equal(await page.locator('.kura-sizes button').count(), 4);
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  await page.getByRole('combobox', { name: 'Evidence kind', exact: true }).selectOption('note');
  assert.equal(await page.locator('.kura-bubble').count(), 1);
  await page.locator('.kura-bubble circle').last().click();
  await page.getByText('Read original evidence', { exact: true }).click();
  await page.getByText('Synthetic personal note about networks.', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Find in library', exact: true }).click();
  await page.getByRole('button', { name: 'Topic classification', exact: true }).click();
  await page.locator('.kura-tree-topic').first().waitFor();
  await page.getByRole('button', { name: 'Ask + web', exact: true }).click();
  await page.getByRole('textbox', { name: 'Question or search' }).fill('network structure');
  await page.getByRole('button', { name: 'Ask with library context', exact: true }).click();
  await page.getByText('Synthetic model fixture: networks connect people.', { exact: false }).waitFor();
  assert.equal(await page.locator('.rw-answer').getByRole('link', { name: 'Evidence', exact: true }).count(), 1);
  await page.getByRole('tab', { name: 'Recommendations', exact: true }).click();
  assert.equal(new URL(page.url()).hash, '#/recommendations');
  await page.getByText('Select Refresh to find papers from your liked collection.', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Refresh recommendations', exact: true }).click();
  await page.getByRole('status', { name: 'recommendations: showing 20 of 45', exact: true }).waitFor();
  assert.equal(await page.locator('.rec-seeds ul').isVisible(), false);
  await page.getByText('About these recommendations', { exact: true }).click();
  await page.locator('.rec-seeds summary').click();
  assert.equal(await page.locator('.rec-seeds ul').isVisible(), true);
  await page.getByText('About these recommendations', { exact: true }).click();
  assert.equal(await page.locator('.rec-seeds ul').isVisible(), false);
  assert.equal(await page.locator('.rec-papers > li').count(), 20);
  await page.getByRole('button', { name: 'Show more recommendations', exact: true }).click();
  assert.equal(await page.locator('.rec-papers > li').count(), 40);
  await page.getByRole('button', { name: 'Show more recommendations', exact: true }).click();
  assert.equal(await page.locator('.rec-papers > li').count(), 45);
  assert.equal(await page.getByRole('button', { name: 'Show more recommendations', exact: true }).count(), 0);
  await page.getByRole('searchbox', { name: 'Search recommendations', exact: true }).fill('recommendation 45:');
  assert.equal(await page.locator('.rec-papers > li').count(), 1);
  await page.getByRole('searchbox', { name: 'Search recommendations', exact: true }).fill('');
  assert.equal(await page.locator('.rec-papers > li').count(), 20);
  await page.reload();
  await page.getByRole('status', { name: 'recommendations: showing 20 of 45', exact: true }).waitFor();
  await saveScreenshot(page, 'recommendations-preview.png');
  console.log(JSON.stringify({ passed: ['native research routes and pairing', 'whole-vault annotation search', 'source-linked wiki build and validated synthesis fixture', 'wiki lint', 'Cytoscape neighborhood expansion, cited connection inspector and direct graph links', 'Kura map, hierarchy, sizes, filtering, original annotations and personal notes, persistence', 'answer context and enabled web boundary with model fixture', 'liked-paper recommendation seeds, cache-only reads, direct routes, search and 20/40/45 disclosure'], liveModelCalled: false }));
} finally {
  await context.close();
  await fs.rm(profile, { recursive: true, force: true });
}
