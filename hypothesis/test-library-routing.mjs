/** Browser routing checks using temporary synthetic library fixtures. */
import assert from 'node:assert/strict';
import { readFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { createServer } from 'node:http';
import { chromium } from './client/node_modules/playwright/index.mjs';
import { buildLibraryTestFixture } from './library-test-fixture.mjs';

const fixture = await buildLibraryTestFixture();

const files = {
  '/': ['index.html', 'text/html'],
  '/fixture.js': ['fixture.js', 'text/javascript'],
  '/sidebar.css': ['sidebar.css', 'text/css'],
};
for (const weight of ['regular', 'medium', 'semibold', 'bold']) {
  const font = `fonts/host-grotesk-${weight}.ttf`;
  files[`/${font}`] = [font, 'font/ttf'];
}
const server = createServer(async (request, response) => {
  const file = files[new URL(request.url, 'http://localhost').pathname];
  if (!file) {
    response.writeHead(404).end();
    return;
  }
  try {
    const body = await readFile(
      path.join(fixture, file[0]),
    );
    response.writeHead(200, { 'Content-Type': file[1] }).end(body);
  } catch {
    response.writeHead(500).end('Unable to read the temporary library test fixture.');
  }
});
let browser;
try {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}/?local-library=1&design=compact`;
  browser = await chromium.launch({
    headless: true,
    executablePath: process.env.HYPOTHESIS_CHROMIUM_PATH,
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const unexpectedActions = [];
  await context.exposeFunction('__recordRouteAction', action =>
    unexpectedActions.push(action),
  );
  await context.addInitScript(() => {
    // Supply existing wiki/atlas results so direct links need no model action.
    Object.defineProperty(globalThis, 'chrome', {
      configurable: true,
      set(value) {
        const original = value.runtime.sendMessage;
        value.runtime.sendMessage = async message => {
          if (
            ['research', 'organize', 'sync', 'enrich-library'].includes(
              message.action,
            )
          ) {
            await globalThis.__recordRouteAction(message.action);
          }
          if (message.action === 'wiki') {
            return {
              ok: true,
              data: {
                stale: false,
                pages: [0, 1].map(index => ({
                  id: `topic-demo-${index}`,
                  title: `Routing topic ${index}`,
                  kind: 'topic',
                  markdown: `# Routing topic ${index}\n\nSynthetic existing wiki content.`,
                  related: [],
                  provider: 'local',
                  evidence_ids: ['demo-0-a0'],
                })),
              },
            };
          }
          if (message.action === 'kura') {
            return {
              ok: true,
              data: {
                available: true,
                stale: false,
                runtime_ready: true,
                current_counts: { annotation: 1, note: 0 },
                counts: { annotation: 1, note: 0 },
                clusters: [
                  {
                    id: 'cluster-demo',
                    name: 'Routing cluster',
                    description: 'Synthetic existing atlas result.',
                    count: 1,
                    chat_ids: ['demo-0-a0'],
                    parent_id: null,
                    children: [],
                    root_id: 'cluster-demo',
                    level: 0,
                    x: 0,
                    y: 0,
                  },
                ],
              },
            };
          }
          if (message.action === 'kura-members') {
            return {
              ok: true,
              data: { total: 0, offset: 0, limit: 50, results: [] },
            };
          }
          const result = await original(message);
          if (result.data?.document) {
            result.data.document.reference_notes = Array.from({ length: 45 }, (_, index) => `Synthetic Zotero note ${index}`);
            result.data.document.reference_tags = Array.from({ length: 45 }, (_, index) => `Synthetic Zotero tag ${index}`);
          }
          return result;
        };
        Object.defineProperty(globalThis, 'chrome', {
          configurable: true,
          writable: true,
          value,
        });
      },
    });
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const route = hash => page.waitForURL(url => url.hash === hash);
  const details = page.getByRole('complementary', {
    name: 'Page details: Attention Is All You Need',
    exact: true,
  });

  await page.goto(base);
  await route('#/library');
  await page.locator('tbody tr').first().waitFor();
  const searchArea = page.locator('.ld-search-area');
  assert.equal(await searchArea.isVisible(), true);
  await page.evaluate(() => {
    globalThis.routingMarker = true;
  });
  await page.getByRole('tab', { name: 'Dashboard', exact: true }).click();
  await route('#/dashboard');
  assert.equal(await searchArea.isVisible(), false);
  const historyLength = await page.evaluate(() => history.length);
  await page.getByRole('tab', { name: 'Dashboard', exact: true }).click();
  assert.equal(await page.evaluate(() => history.length), historyLength);
  assert.equal(
    await page.evaluate(() => globalThis.routingMarker),
    true,
    'Navigation reloaded the document',
  );
  await page.goBack();
  await route('#/library');
  assert.equal(await searchArea.isVisible(), true);
  assert.equal(
    await page
      .getByRole('tab', { name: /Library/ })
      .getAttribute('aria-selected'),
    'true',
  );
  await page.goForward();
  await route('#/dashboard');

  for (const title of ['Annotations', 'Pages']) {
    for (const dimension of ['topic', 'keyword', 'authors']) {
      await page.getByRole('heading', { name: `${title} by ${dimension}`, exact: true }).waitFor();
    }
  }
  if (process.env.HYPOTHESIS_DASHBOARD_SCREENSHOT) {
    await page.locator('.library-insights').screenshot({ path: process.env.HYPOTHESIS_DASHBOARD_SCREENSHOT });
  }
  for (const [dimension, label, count] of [
    ['topic', 'Language models and artificial intelligence', 2],
    ['keyword', 'Machine learning', 2],
    ['authors', 'Ashish Vaswani', 1],
  ]) {
    const chart = page.getByRole('list', { name: `Pages by ${dimension}`, exact: true });
    await chart.getByRole('button', {
      name: `${label}: ${count} ${count === 1 ? 'page' : 'pages'}. Filter`,
      exact: true,
    }).click();
    await route('#/library');
    assert.equal(await page.locator('tbody tr').count(), count);
    await page.getByRole('button', { name: 'Clear all', exact: true }).click();
    await page.getByRole('tab', { name: 'Dashboard', exact: true }).click();
    await route('#/dashboard');
  }

  await page.getByRole('tab', { name: 'Collections', exact: true }).click();
  await route('#/collections');
  assert.equal(await searchArea.isVisible(), false);
  await page
    .locator('.ld-rail-collections a[href="#/collections/For%20later"]')
    .click();
  await route('#/collections/For%20later');
  await page.reload();
  await page.locator('tbody tr').first().waitFor();
  assert.equal(await searchArea.isVisible(), false);
  assert.equal(
    await page.getByRole('heading', { level: 1 }).innerText(),
    'For later.',
  );
  await page
    .locator('.ld-rail-collections a[href="#/collections/Likes"]')
    .click();
  await page
    .getByRole('button', { name: 'Attention Is All You Need', exact: true })
    .click();
  await route('#/collections/Likes/pages/demo-0');
  await details.waitFor();
  const importedNotes = details.getByRole('region', { name: 'Imported reference notes', exact: true });
  const importedTags = details.getByRole('region', { name: 'Imported reference tags', exact: true });
  await importedNotes.getByRole('status', { name: 'imported notes: showing 20 of 45', exact: true }).waitFor();
  await importedTags.getByRole('status', { name: 'imported tags: showing 20 of 45', exact: true }).waitFor();
  await importedNotes.getByRole('button', { name: 'Show more imported notes', exact: true }).click();
  await importedNotes.getByRole('status', { name: 'imported notes: showing 40 of 45', exact: true }).waitFor();
  await importedTags.getByRole('status', { name: 'imported tags: showing 20 of 45', exact: true }).waitFor();
  await importedNotes.getByRole('button', { name: 'Show more imported notes', exact: true }).click();
  await importedNotes.getByRole('status', { name: 'imported notes: showing 45 of 45', exact: true }).waitFor();
  assert.equal(await importedNotes.getByRole('button', { name: 'Show more imported notes', exact: true }).count(), 0);
  await page.reload();
  await details.waitFor();
  await page
    .getByRole('button', { name: 'Close page details', exact: true })
    .click();
  await route('#/collections/Likes');
  await page.goBack();
  await route('#/collections/Likes/pages/demo-0');
  await details.waitFor();
  await page.keyboard.press('Escape');
  await route('#/collections/Likes');
  await details.waitFor({ state: 'detached' });

  await page.goto(`${base}#/research/wiki/topic-demo-0`);
  await page.getByRole('region', { name: 'Developer mode required' }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Wiki', exact: true }).count(), 0);
  await page.getByRole('button', { name: 'Enable developer mode', exact: true }).click();
  await page
    .getByRole('heading', { name: 'Routing topic 0', level: 2, exact: true })
    .waitFor();
  await page
    .getByRole('navigation', { name: 'Wiki pages', exact: true })
    .getByRole('button')
    .nth(1)
    .click();
  await route('#/research/wiki/topic-demo-1');
  await page.reload();
  await page
    .getByRole('heading', { name: 'Routing topic 1', level: 2, exact: true })
    .waitFor();
  await page.getByText('Update settings', { exact: true }).click();
  const autoWiki = page.getByRole('checkbox', {
    name: /Update Wiki automatically/,
  });
  const autoGraph = page.getByRole('checkbox', {
    name: /Refresh Knowledge graph automatically/,
  });
  assert.equal(await autoWiki.isChecked(), false);
  await autoWiki.check();
  await autoGraph.uncheck();
  await page
    .getByRole('combobox', { name: 'Refresh interval', exact: true })
    .selectOption('30000');
  await page.reload();
  await page
    .getByRole('heading', { name: 'Routing topic 1', level: 2, exact: true })
    .waitFor();
  await page.getByText('Update settings', { exact: true }).click();
  assert.equal(await autoWiki.isChecked(), true);
  assert.equal(await autoGraph.isChecked(), false);
  assert.equal(
    await page
      .getByRole('combobox', { name: 'Refresh interval', exact: true })
      .inputValue(),
    '30000',
  );
  await page
    .getByRole('button', { name: 'Refresh saved Wiki', exact: true })
    .click();
  await page
    .getByRole('heading', { name: 'Routing topic 1', level: 2, exact: true })
    .waitFor();
  if (process.env.HYPOTHESIS_UPDATES_SCREENSHOT) {
    await page.screenshot({ path: process.env.HYPOTHESIS_UPDATES_SCREENSHOT });
  }
  await page
    .getByRole('button', { name: 'Knowledge graph', exact: true })
    .click();
  await route('#/research/graph');
  await page.getByRole('img', { name: /Knowledge graph with/ }).waitFor();
  await page
    .getByRole('button', { name: 'Refresh graph', exact: true })
    .click();
  await page.reload();
  await page.getByRole('img', { name: /Knowledge graph with/ }).waitFor();
  await page
    .getByRole('button', { name: 'Find in library', exact: true })
    .click();
  await route('#/research/find');
  await page
    .getByRole('heading', {
      name: 'Find in library',
      exact: true,
    })
    .waitFor();

  await page.goto(`${base}#/settings`);
  await page.getByRole('checkbox', { name: 'Enable developer mode', exact: true }).uncheck();
  await page.reload();
  assert.equal(await page.getByRole('checkbox', { name: 'Enable developer mode', exact: true }).isChecked(), false);
  await page.goto(`${base}#/research/graph`);
  await page.getByRole('region', { name: 'Developer mode required' }).waitFor();
  assert.equal(await page.getByRole('img', { name: /Knowledge graph with/ }).count(), 0);
  await page.getByRole('button', { name: 'Enable developer mode', exact: true }).click();
  await page.getByRole('img', { name: /Knowledge graph with/ }).waitFor();

  await page.getByRole('button', { name: 'Topic classification', exact: true }).click();
  await route('#/research/kura/hierarchy');
  await page.getByRole('heading', { name: 'Topic classification', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Map', exact: true }).click();
  await route('#/research/kura/map');
  await page.reload();
  await page.getByRole('group', { name: 'Kura cluster map', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Topic sizes', exact: true }).click();
  await route('#/research/kura/sizes');
  await page.locator('.kura-legend button').click();
  await route('#/research/kura/sizes/clusters/cluster-demo');
  await page.reload();
  await page
    .getByRole('complementary', { name: 'Cluster evidence', exact: true })
    .getByRole('heading', { name: 'Routing cluster', exact: true })
    .waitFor();
  await page
    .getByRole('button', { name: 'Refresh saved results', exact: true })
    .click();

  await page.goto(`${base}&tab=dashboard`);
  await route('#/dashboard');
  await page.goto(`${base}#/library/pages/missing-page`);
  await page
    .getByRole('alert')
    .filter({ hasText: 'This saved page is no longer in your library.' })
    .waitFor();
  await page
    .getByRole('button', { name: 'Close page details', exact: true })
    .click();
  await route('#/library');
  await page.goto(`${base}#/%E0%A4%A`);
  await route('#/library');
  await page.locator('tbody tr').first().waitFor();
  assert.equal(new URL(page.url()).searchParams.get('local-library'), '1');
  assert.equal(await page.getByRole('button', { name: 'Back up now', exact: true }).count(), 0);
  assert.equal(await page.getByRole('button', { name: 'Enrich research', exact: true }).count(), 0);
  await page.getByRole('tab', { name: 'Settings', exact: true }).click();
  await route('#/settings');
  const autoBackup = page.getByRole('checkbox', { name: 'Back up automatically every day', exact: true });
  const autoEnrich = page.getByRole('checkbox', { name: 'Enrich research automatically', exact: true });
  const openalexKey = page.getByLabel('OpenAlex API key', { exact: true });
  const saveSettings = page.getByRole('button', { name: 'Save settings', exact: true });
  const mode = page.getByRole('combobox', { name: 'Color mode', exact: true });
  await page.getByRole('region', { name: 'Zotero integration', exact: true }).waitFor();
  await page.getByLabel('Zotero API key', { exact: true }).waitFor();
  assert.equal(await page.getByLabel('Zotero API key', { exact: true }).inputValue(), '');
  assert.equal(await page.getByRole('button', { name: 'Import from Zotero online', exact: true }).isDisabled(), true);
  assert.equal(await page.getByRole('button', { name: 'Import from Zotero desktop', exact: true }).isEnabled(), true);
  const expectMode = value => page.waitForFunction(value => document.querySelector('.ld-app')?.getAttribute('data-color-scheme') === value, value);
  await mode.selectOption('system');
  await page.emulateMedia({ colorScheme: 'dark' });
  await expectMode('dark');
  await page.emulateMedia({ colorScheme: 'light' });
  await expectMode('light');
  await mode.selectOption('dark');
  await expectMode('dark');
  await page.reload();
  await expectMode('dark');
  assert.equal(await mode.inputValue(), 'dark');
  assert.equal(await page.evaluate(async () => { await document.fonts.ready; return document.fonts.check('16px "Host Grotesk"'); }), true);
  assert.equal(await page.getByRole('group', { name: 'Design options', exact: true }).count(), 0);
  await page.getByRole('button', { name: 'Switch to light mode', exact: true }).click();
  await expectMode('light');
  assert.equal(await mode.inputValue(), 'light');
  await page.getByRole('button', { name: 'Switch to dark mode', exact: true }).click();
  await expectMode('dark');
  await page.getByRole('tab', { name: 'Dashboard', exact: true }).click();
  await route('#/dashboard');
  await page.getByRole('heading', { name: 'Reading activity', exact: true }).waitFor();
  const activity = page.getByRole('region', { name: 'Reading activity over time', exact: true });
  const interval = activity.getByRole('group', { name: 'Activity interval', exact: true });
  await interval.getByRole('button', { name: 'Daily', exact: true }).click();
  await activity.getByRole('combobox', { name: 'Activity period', exact: true }).selectOption('90');
  await activity.locator('.ld-chart-table summary').click();
  assert.equal(await activity.locator('tbody tr').count(), 20);
  assert.equal(await activity.locator('.ld-line-chart circle').count(), 90);
  await activity.getByRole('button', { name: 'Show more activity periods', exact: true }).click();
  assert.equal(await activity.locator('tbody tr').count(), 40);
  await interval.getByRole('button', { name: 'Weekly', exact: true }).click();
  assert.equal(await activity.locator('tbody tr').count(), 12);
  assert.equal(await activity.getByRole('combobox', { name: 'Activity period', exact: true }).inputValue(), '12');
  await activity.getByRole('combobox', { name: 'Activity period', exact: true }).selectOption('26');
  assert.equal(await activity.locator('tbody tr').count(), 20);
  await activity.getByRole('combobox', { name: 'Activity period', exact: true }).selectOption('4');
  assert.equal(await activity.locator('tbody tr').count(), 4);
  await activity.getByRole('combobox', { name: 'Activity period', exact: true }).selectOption('12');
  assert.equal(await activity.locator('tbody tr').count(), 12);
  await page.reload();
  assert.equal(await interval.getByRole('button', { name: 'Weekly', exact: true }).getAttribute('aria-pressed'), 'true');
  await interval.getByRole('button', { name: 'Daily', exact: true }).click();
  assert.equal(await activity.getByRole('combobox', { name: 'Activity period', exact: true }).inputValue(), '90');
  await interval.getByRole('button', { name: 'Monthly', exact: true }).click();
  assert.equal(await activity.getByRole('combobox', { name: 'Activity period', exact: true }).inputValue(), '6');
  if (process.env.HYPOTHESIS_DARK_SCREENSHOT) {
    await page.screenshot({ path: process.env.HYPOTHESIS_DARK_SCREENSHOT });
  }
  await page.getByRole('tab', { name: 'Library', exact: false }).click();
  await route('#/library');
  await page.getByRole('table', { name: 'Reading library table', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Attention Is All You Need', exact: true }).click();
  await details.waitFor();
  if (process.env.HYPOTHESIS_DARK_DETAILS_SCREENSHOT) {
    await page.screenshot({ path: process.env.HYPOTHESIS_DARK_DETAILS_SCREENSHOT });
  }
  await page.getByRole('button', { name: 'Close page details', exact: true }).click();
  await page.getByRole('tab', { name: 'Settings', exact: true }).click();
  await route('#/settings');
  await autoBackup.waitFor();
  assert.equal(await autoBackup.isChecked(), false);
  assert.equal(await openalexKey.getAttribute('type'), 'password');
  await autoBackup.check();
  await autoEnrich.uncheck();
  await page.getByLabel('Daily backup time', { exact: true }).fill('04:30');
  await openalexKey.fill('synthetic-preview-api-key');
  await saveSettings.click();
  await page.getByRole('status').filter({ hasText: 'Settings saved.' }).waitFor();
  assert.equal(await openalexKey.inputValue(), '');
  assert.equal(await page.evaluate(() => JSON.stringify(sessionStorage).includes('synthetic-preview-api-key')), false);
  await page.reload();
  await route('#/settings');
  await autoBackup.waitFor();
  assert.equal(await autoBackup.isChecked(), true);
  assert.equal(await autoEnrich.isChecked(), false);
  assert.equal(await page.getByLabel('Daily backup time', { exact: true }).inputValue(), '04:30');
  assert.equal(await openalexKey.inputValue(), '');
  assert.match(await openalexKey.getAttribute('placeholder'), /Configured/);
  if (process.env.HYPOTHESIS_SETTINGS_SCREENSHOT) {
    await page.screenshot({ path: process.env.HYPOTHESIS_SETTINGS_SCREENSHOT, fullPage: true });
  }
  await page.getByRole('button', { name: 'Back up now', exact: true }).click();
  await page.getByRole('button', { name: 'Enrich research', exact: true }).click();
  // A failed save keeps the user's draft available for retry.
  await page.evaluate(() => {
    const original = chrome.runtime.sendMessage;
    chrome.runtime.sendMessage = async message => {
      if (message.action === 'save-settings') {
        chrome.runtime.sendMessage = original;
        return { ok: false, error: 'Synthetic settings save failure' };
      }
      return original(message);
    };
  });
  await openalexKey.fill('synthetic-replacement-key');
  await saveSettings.click();
  await page.getByRole('alert').filter({ hasText: 'Synthetic settings save failure' }).waitFor();
  assert.equal(await openalexKey.inputValue(), 'synthetic-replacement-key');
  await saveSettings.click();
  await page.getByRole('status').filter({ hasText: 'Settings saved.' }).waitFor();
  assert.equal(await openalexKey.inputValue(), '');
  await page.getByRole('button', { name: 'Remove key', exact: true }).click();
  await saveSettings.click();
  await page.getByRole('status').filter({ hasText: 'Settings saved.' }).waitFor();
  assert.equal(await openalexKey.getAttribute('placeholder'), 'Enter API key');
  // Only the explicit enrichment click above may start an enrichment job.
  assert.deepEqual(unexpectedActions.splice(0), ['enrich-library']);
  assert.deepEqual(
    unexpectedActions,
    [],
    'Opening routes must not start model or library mutation jobs',
  );
  const title = 'Attention Is All You Need';
  const remove = page.getByRole('button', { name: `Remove from library: ${title}`, exact: true });
  const pageTitle = page.getByRole('button', { name: title, exact: true });
  for (const design of ['compact', 'studio', 'paper', 'classic']) {
    await page.goto(`${base.replace('design=compact', `design=${design}`)}#/library`);
    await remove.waitFor();
    assert.equal(await page.getByTestId('local-library').getAttribute('data-design'), 'compact');
    assert.equal(await page.getByRole('group', { name: 'Design options', exact: true }).count(), 0);
    assert.equal(await page.getByRole('table', { name: 'Reading library table', exact: true }).count(), 1);
    const count = await page.locator('.ld-library-summary').innerText();
    await remove.click();
    await remove.waitFor({ state: 'detached' });
    assert.equal(await pageTitle.count(), 0);
    assert.notEqual(await page.locator('.ld-library-summary').innerText(), count);
    await route('#/library');
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await remove.waitFor();
    assert.equal(await page.locator('.ld-library-summary').innerText(), count);
  }
  await page.goto(`${base.replace('design=compact', 'view=list')}#/library/pages/demo-0`);
  await details.waitFor();
  assert.equal(await page.getByTestId('local-library').getAttribute('data-design'), 'compact');
  await page.getByRole('button', { name: 'Close page details', exact: true }).click();
  await route('#/library');
  // A failed removal leaves the row intact and offers the actual error.
  await page.evaluate(() => {
    const original = chrome.runtime.sendMessage;
    chrome.runtime.sendMessage = async message => {
      if (message.action === 'remove') {
        chrome.runtime.sendMessage = original;
        return { ok: false, error: 'Synthetic removal failure' };
      }
      return original(message);
    };
  });
  await remove.click();
  await page.getByRole('alert').filter({ hasText: 'Synthetic removal failure' }).waitFor();
  assert.equal(await remove.isEnabled(), true);
  await remove.click();
  await remove.waitFor({ state: 'detached' });
  await page.reload();
  await page.locator('tbody tr').first().waitFor();
  assert.equal(await pageTitle.count(), 0, 'Removed pages must stay removed on refresh');
  await page.getByRole('tab', { name: 'Recommendations', exact: true }).click();
  await route('#/recommendations');
  await page.getByRole('region', { name: 'Paper recommendations', exact: true }).waitFor();
  assert.equal(await searchArea.isVisible(), false);
  await page.reload();
  await page.getByRole('region', { name: 'Paper recommendations', exact: true }).waitFor();
  assert.equal(await page.getByRole('tab', { name: 'Recommendations', exact: true }).getAttribute('aria-selected'), 'true');
  assert.equal(await page.getByRole('link', { name: 'sidenote home', exact: true }).isVisible(), true);
  assert.equal(await page.locator('.ld-brand svg').count(), 1);
  assert.deepEqual(errors, []);
  if (process.env.HYPOTHESIS_ROUTING_SCREENSHOT) {
    await page.screenshot({ path: process.env.HYPOTHESIS_ROUTING_SCREENSHOT });
  }
  console.log(
    'PASS: Compact-only layout, Console dark mode and System preference, legacy links, routing, Settings, write-only keys, maintenance, removal/Undo, and failure recovery.',
  );
} finally {
  try {
    await browser?.close();
  } finally {
    if (server.listening) {
      await new Promise(resolve => server.close(resolve));
    }
    await rm(fixture, { recursive: true, force: true });
  }
}
