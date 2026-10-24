import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { chromium } from './client/node_modules/playwright/index.mjs';
import { saveScreenshot } from './test-screenshots.mjs';

const root = path.dirname(new URL(import.meta.url).pathname);
const config = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
const extension = path.join(root, 'browser-extension/build');
const manifest = JSON.parse(await fs.readFile(path.join(extension, 'manifest.json'), 'utf8'));
const localId = createHash('sha256').update(Buffer.from(manifest.key, 'base64')).digest('hex').slice(0,32).replace(/[0-9a-f]/g, digit => String.fromCharCode(97 + Number.parseInt(digit, 16)));
assert.notEqual(localId, 'bjfhmglciegochdpefhhlphglcehbmek');
assert.equal(manifest.name, 'sidenote');
assert.equal(manifest.short_name, 'sidenote');
assert.equal(localId, 'lebpfahhlannplfhlllolppkmcapecge');
assert.equal(manifest.icons['128'], 'images/sidenote128.png');
assert.equal(manifest.homepage_url, 'https://github.com/YXGuan/sidenote');
const cache = path.join(os.homedir(), 'Library/Caches/ms-playwright');
let executablePath = process.env.HYPOTHESIS_CHROMIUM_PATH;
if (!executablePath && process.platform === 'darwin') {
  for (const name of (await fs.readdir(cache).catch(() => [])).filter(name => /^chromium-\d+$/.test(name)).sort().reverse()) {
    const candidate = path.join(cache, name, 'chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing');
    try { await fs.access(candidate); executablePath = candidate; break; } catch {}
  }
}
const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'hypothesis-native-chrome-'));
const extensions = [extension];
if (process.env.HYPOTHESIS_OFFICIAL_EXTENSION) {
  const official = path.join(profile, 'official-extension');
  await fs.cp(process.env.HYPOTHESIS_OFFICIAL_EXTENSION, official, { recursive: true });
  await fs.rm(path.join(official, '_metadata'), { recursive: true, force: true });
  extensions.push(official);
}
const context = await chromium.launchPersistentContext(profile, {
  executablePath, headless: true, viewport: {width:1280,height:900},
  ignoreDefaultArgs: ['--disable-extensions'],
  args: [`--disable-extensions-except=${extensions.join(',')}`, `--load-extension=${extensions.join(',')}`],
});
const failures = [];
const apiRequests = [];
try {
  const fixtureIndex = JSON.parse((await fs.readFile(path.join(root, 'client/src/sidebar/services/test/api-index.json'), 'utf8')).replaceAll('https://example.com', 'https://hypothes.is'));
  fixtureIndex.links.profile.groups={read:{url:'https://hypothes.is/api/profile/groups',method:'GET',desc:'Profile groups'}};
  const group = {id:'__world__',name:'Public',type:'open',organization:{id:'__default__',name:'Hypothesis',logo:''},scopes:null,links:{html:'https://hypothes.is/groups/__world__'},pre_moderated:false};
  let annotation = config.annotation;
  let cloudSaves = 0;
  await context.route('https://hypothes.is/api/**', async route => {
    const url = new URL(route.request().url());
    apiRequests.push(url.pathname + url.search);
    let result;
    if (url.pathname === '/api/' || url.pathname === '/api') result = fixtureIndex;
    else if (url.pathname === '/api/profile') {
      const loggedIn = route.request().headers().authorization === 'Bearer synthetic-local-account-token';
      result = {authority:'hypothes.is',userid:loggedIn ? 'acct:demo-reader@hypothes.is' : null,user_info:loggedIn ? {display_name:'Demo Reader'} : null,features:{},preferences:{}};
    }
    else if (url.pathname === '/api/profile/groups') result = [group];
    else if (url.pathname === '/api/groups') result = [group];
    else if (url.pathname.startsWith('/api/groups/')) result = group;
    else if (url.pathname === '/api/links') result = {'user':'https://hypothes.is/users/:user','search.tag':'https://hypothes.is/search?q=tag::tag','account.settings':'https://hypothes.is/account/settings','groups.new':'https://hypothes.is/groups/new','help':'https://web.hypothes.is/help/'};
    else if (url.pathname === '/api/search') result = {total:1,rows:[annotation]};
    else if (url.pathname === '/api/badge') result = {total:1};
    else if (url.pathname.startsWith('/api/annotations/')) {
      if (route.request().method() !== 'GET') {
        assert.equal(route.request().headers().authorization, 'Bearer synthetic-local-account-token');
        cloudSaves++;
        annotation = {...annotation,...route.request().postDataJSON(),document:config.annotation.document};
      }
      result = annotation;
    } else { result = {}; failures.push(url.pathname); }
    await route.fulfill({contentType:'application/json',body:JSON.stringify(result)});
  });
  await context.route('https://hypothes.is/welcome', route=>route.fulfill({contentType:'text/html',body:'<title>Hypothesis test</title>'}));
  await context.route('https://hyp.is/**', route=>route.fulfill({contentType:'text/html',body:'<title>Hypothesis activation</title>'}));
  await context.route('https://example.org/paper', route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><head><title>Learning across a lifetime</title><meta name="citation_author" content="Ada Reader"><meta name="citation_author_institution" content="Example University"><meta name="citation_journal_title" content="Learning Journal"></head><body style="max-width:680px;margin:70px auto;font:18px/1.7 Georgia"><h1>Learning across a lifetime</h1><p>Reading is more useful when ideas stay connected.</p><p>A synthetic research document for testing the original Hypothesis annotation client.</p></body></html>'}));
  const worker = context.serviceWorkers().find(worker=>new URL(worker.url()).host === localId) || await context.waitForEvent('serviceworker', {predicate:worker=>new URL(worker.url()).host === localId});
  const id = new URL(worker.url()).host;
  if (extensions.length === 2) {
    const officialWorker = context.serviceWorkers().find(worker=>new URL(worker.url()).host === 'bjfhmglciegochdpefhhlphglcehbmek') || await context.waitForEvent('serviceworker', {predicate:worker=>new URL(worker.url()).host === 'bjfhmglciegochdpefhhlphglcehbmek'});
    assert.equal(await officialWorker.evaluate(()=>chrome.runtime.getManifest().name), 'Hypothesis - Web & PDF Annotation');
    assert.equal(await worker.evaluate(()=>chrome.runtime.getManifest().name), 'sidenote');
  }
  await worker.evaluate(async ({port,key})=>{
    await chrome.storage.local.set({researchKey:key,researchAutoTags:true});
    const realFetch=globalThis.fetch.bind(globalThis);
    globalThis.fetch=(url,options)=>{
      if (String(url).endsWith('/api/suggest-page') && String(url).startsWith('http://127.0.0.1:8765')) return (async () => {
        const response = await realFetch(`http://127.0.0.1:${port}/api/document?url=${encodeURIComponent('https://example.org/paper')}`, {headers:options.headers});
        const {document} = await response.json();
        return new Response(JSON.stringify({document:{...document,auto_tags:['contextual-learning','evidence'],analysis:{tags:['contextual-learning','evidence'],sentiments:[]}}}), {headers:{'Content-Type':'application/json'}});
      })();
      return realFetch(String(url).replace('http://127.0.0.1:8765',`http://127.0.0.1:${port}`),options);
    };
  },config);
  const page = await context.newPage();
  page.on('pageerror',error=>failures.push(error.message));
  await page.goto('https://hyp.is/');
  await page.evaluate(async id=>chrome.runtime.sendMessage(id,{type:'activate',url:'https://example.org/paper'}),id);
  await page.waitForURL('https://example.org/paper');
  await page.waitForSelector(`iframe[src^="chrome-extension://${id}/client/"]`,{state:'attached',timeout:20000});
  const sidebar=page.frames().find(frame=>frame.url().startsWith(`chrome-extension://${id}/client/`));
  assert(sidebar,'Original sidebar iframe did not load');
  const toolbar = page.getByRole('button', {name:'Annotation sidebar',exact:true});
  await toolbar.waitFor({timeout:10000});
  await toolbar.click();
  await sidebar.getByRole('button',{name:'Log in',exact:true}).click();
  await sidebar.getByRole('button',{name:'Edit',exact:true}).waitFor();
  assert(await sidebar.evaluate(()=>localStorage.getItem('hypothesis.local-account.enabled') === 'true'));
  assert(await sidebar.evaluate(()=>!Object.values(localStorage).some(value=>String(value).includes('synthetic-local-account-token'))), 'Account token must not be persisted in browser storage');
  await sidebar.getByRole('button',{name:'Like this annotation',exact:true}).click();
  await sidebar.waitForFunction(()=>document.querySelector('button[aria-label="Like this annotation"]')?.getAttribute('aria-pressed')==='true');
  await sidebar.getByRole('button',{name:'Annotation sentiment',exact:true}).click();
  assert.equal(await sidebar.getByRole('textbox',{name:'Personal title',exact:true}).count(), 0, 'Page title leaked into annotation controls');
  await sidebar.getByRole('button',{name:'Annotation sentiment',exact:true}).click();
  await saveScreenshot(page, 'native-hypothesis-preview.png', {fullPage:true});
  await sidebar.getByRole('button',{name:'Edit',exact:true}).click();
  await sidebar.locator('textarea').first().fill('Saved through the original Hypothesis account workflow.');
  await sidebar.getByRole('button',{name:'Post to Public',exact:true}).click();
  await sidebar.getByRole('button',{name:'Edit',exact:true}).waitFor();
  assert.equal(cloudSaves, 1, 'Original cloud save was not called');
  await sidebar.getByRole('tab',{name:/Page Notes/i}).click();
  await sidebar.getByText('Example University',{exact:false}).waitFor();
  await sidebar.getByRole('textbox',{name:'Personal title',exact:true}).fill('My native Hypothesis title');
  await sidebar.getByRole('button',{name:'Save title',exact:true}).click();
  await sidebar.getByRole('list',{name:'Auto tags',exact:true}).getByText('contextual-learning',{exact:true}).waitFor();
  await sidebar.getByPlaceholder('Add new tags',{exact:true}).fill('hand-picked');
  await sidebar.getByPlaceholder('Add new tags',{exact:true}).press('Enter');
  try { await sidebar.getByRole('list',{name:'Manual tags',exact:true}).getByText('hand-picked',{exact:true}).waitFor({timeout:10000}); } catch (error) { console.log(JSON.stringify({stage:'manual-tag',text:await sidebar.locator('body').innerText()})); throw error; }
  assert.equal(await sidebar.getByRole('list',{name:'Manual tags',exact:true}).getByText('contextual-learning',{exact:true}).count(),0);
  await sidebar.getByRole('button',{name:'Page reaction: Like',exact:true}).click();
  await sidebar.waitForFunction(()=>document.querySelector('button[title="Page reaction: Like"]')?.getAttribute('aria-pressed')==='true');
  await sidebar.getByRole('checkbox',{name:'Likes',exact:true}).check();
  await sidebar.getByRole('checkbox',{name:'For later',exact:true}).check();
  await sidebar.getByRole('textbox',{name:'New group',exact:true}).fill('Lab reading');
  await sidebar.getByRole('button',{name:'Add group',exact:true}).click();
  await sidebar.getByRole('checkbox',{name:'Lab reading',exact:true}).check();
  assert.equal(cloudSaves, 1, 'Page edits must stay local');
  await saveScreenshot(page, 'native-document-details-preview.png', {fullPage:true});
  await saveScreenshot(page, 'native-tag-editor-preview.png', {fullPage:true});
  await sidebar.getByRole('tab',{name:/Annotations/i}).click();
  assert.equal(await sidebar.locator('[data-testid="page-research"]').count(), 0, 'Page details should be inside Page Notes');
  await worker.evaluate(()=>{
    globalThis.beforeOfflineFetch=globalThis.fetch;
    globalThis.fetch=(url,options)=>String(url).includes('/api/annotation-reaction') ? Promise.reject(new TypeError('Simulated offline service')) : globalThis.beforeOfflineFetch(url,options);
  });
  await sidebar.getByRole('button',{name:'Like this annotation',exact:true}).click();
  await sidebar.getByRole('alert').filter({hasText:'Start the local'}).waitFor();
  assert(await sidebar.getByRole('button',{name:'Edit',exact:true}).isVisible(),'Normal Hypothesis actions disappeared while local storage was offline');
  await worker.evaluate(()=>{globalThis.fetch=globalThis.beforeOfflineFetch;});
  // Reproduce a refreshed dashboard talking to an older loaded worker: its
  // library action works, while the optional organization action is missing.
  await worker.evaluate(()=>{
    globalThis.beforeCapabilitiesFetch=globalThis.fetch;
    globalThis.fetch=(url,options)=>String(url).endsWith('/api/organization')
      ? Promise.resolve(new Response(JSON.stringify({error:'Unsupported local research action'}),{status:400,headers:{'Content-Type':'application/json'}}))
      : globalThis.beforeCapabilitiesFetch(url,options);
  });
  const dashboard = await context.newPage();
  dashboard.on('pageerror', error => failures.push(error.message));
  await dashboard.setViewportSize({width:1440,height:1100});
  await dashboard.goto(`chrome-extension://${id}/client/notebook.html?local-library=1`);
  await dashboard.getByRole('heading',{name:'Your library.',exact:true}).waitFor();
  const updateNotice = dashboard.getByRole('complementary', {name:'Dashboard update',exact:true});
  await updateNotice.waitFor();
  assert.equal(await updateNotice.locator('p').isVisible(), false);
  assert.equal(await updateNotice.getByRole('button',{name:'Retry connection',exact:true}).count(), 0);
  await updateNotice.getByText('How to update',{exact:true}).click();
  assert.equal(await updateNotice.locator('p').isVisible(), true);
  const savedTitle = dashboard.getByRole('button',{name:'My native Hypothesis title',exact:true});
  await savedTitle.waitFor();
  assert.equal(await dashboard.locator('tbody tr').count() >= 7, true, 'An optional capability must not hide saved pages');
  await updateNotice.getByRole('button',{name:'Dismiss update notice',exact:true}).click();
  await dashboard.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await updateNotice.waitFor({state:'detached'});
  await dashboard.reload();
  await savedTitle.waitFor();
  assert.equal(await updateNotice.count(), 0);
  await worker.evaluate(()=>{globalThis.fetch=globalThis.beforeCapabilitiesFetch;});
  await dashboard.reload();
  await savedTitle.waitFor();
  assert.equal(await dashboard.getByTestId('local-library').getAttribute('data-design'), 'compact');
  assert.equal(await dashboard.getByTestId('local-library').getAttribute('data-view'), 'table');
  const search = dashboard.getByRole('textbox',{name:'Search local library',exact:true});
  await search.fill('nonexistent research title');
  await dashboard.getByText('No pages match these filters',{exact:true}).waitFor();
  await search.fill('My native');
  await savedTitle.click();
  const details = dashboard.getByRole('complementary', {name:'Page details: My native Hypothesis title',exact:true});
  await details.getByText('Example University',{exact:false}).waitFor();
  assert.equal(await details.getByRole('textbox',{name:'Personal title',exact:true}).isVisible(), true);
  assert.equal(await details.getByRole('list',{name:'Manual tags',exact:true}).isVisible(), true);
  await saveScreenshot(dashboard, 'native-local-library-preview.png', {fullPage:true});
  await dashboard.getByRole('button',{name:'Close page details',exact:true}).click();
  await search.fill('');
  const sort = dashboard.getByRole('combobox',{name:'Sort by',exact:true});
  await sort.selectOption('annotations');
  assert.equal((await dashboard.locator('tbody tr').first().textContent()).includes('Networks and collective behavior'), true);
  await dashboard.reload();
  await savedTitle.waitFor();
  assert.equal(await sort.inputValue(), 'annotations');
  await saveScreenshot(dashboard, 'dashboard-table-preview.png', {animations:'disabled'});
  await dashboard.getByRole('tab',{name:'Dashboard',exact:true}).click();
  await dashboard.getByRole('heading',{name:'Reading dashboard.',exact:true}).waitFor();
  await saveScreenshot(dashboard, 'dashboard-overview-preview.png', {animations:'disabled'});
  await dashboard.getByRole('tab',{name:'Settings',exact:true}).click();
  const provider = dashboard.getByRole('combobox',{name:'Categorize with',exact:true});
  await provider.selectOption('codex');
  await dashboard.getByRole('button',{name:'Organize library',exact:true}).click();
  await dashboard.getByText('Organize with GPT-6 Luna?',{exact:true}).waitFor();
  await dashboard.getByRole('button',{name:'Cancel',exact:true}).click();
  const job = await dashboard.evaluate(async ()=> (await chrome.runtime.sendMessage({type:'local-research',action:'organization'})).data.job);
  assert.equal(job.state,'idle','Cancel must not start organization');
  await provider.selectOption('local');
  await dashboard.getByRole('button',{name:'Organize library',exact:true}).click();
  await dashboard.waitForFunction(async()=> (await chrome.runtime.sendMessage({type:'local-research',action:'organization'})).data.job.state === 'complete');
  await worker.evaluate(()=>{
    globalThis.beforeLibraryOfflineFetch=globalThis.fetch;
    globalThis.fetch=(url,options)=>String(url).endsWith('/api/library')
      ? Promise.reject(new TypeError('Simulated library connection failure'))
      : globalThis.beforeLibraryOfflineFetch(url,options);
  });
  const disconnected = await context.newPage();
  await disconnected.goto(`chrome-extension://${id}/client/notebook.html?local-library=1`);
  await disconnected.getByRole('alert').filter({hasText:'Start the local'}).waitFor();
  assert.equal((await disconnected.locator('.ld-library-summary').innerText()).includes('— saved pages'), true);
  assert.equal(await disconnected.getByText('No saved pages',{exact:true}).count(), 0);
  await worker.evaluate(()=>{globalThis.fetch=globalThis.beforeLibraryOfflineFetch;});
  await disconnected.getByRole('button',{name:'Retry connection',exact:true}).click();
  await disconnected.getByRole('button',{name:'My native Hypothesis title',exact:true}).waitFor();
  await disconnected.close();

  await context.route('https://hypothes.is/users/demo-reader',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><title>Demo Reader — Hypothesis</title><div class="search-result-bucket"><div class="search-result-bucket__title-and-annotations-count"><a class="search-result-bucket__title" href="#">Original publisher title</a><span>1 annotation</span></div><a href="https://hyp.is/native-test-annotation/example.org/paper">Source</a></div>'}));
  await page.goto('https://hypothes.is/users/demo-reader');
  await page.getByRole('button',{name:'Edit personal title',exact:true}).waitFor();
  assert.equal(await page.locator('.search-result-bucket__title').textContent(),'My native Hypothesis title');
  await page.getByRole('button',{name:'Edit personal title',exact:true}).click();
  await page.getByRole('textbox',{name:'Personal title',exact:true}).fill('Updated on the original profile');
  await page.getByRole('button',{name:'Save',exact:true}).click();
  await page.getByText('Updated on the original profile',{exact:true}).waitFor();
  await page.reload();
  await page.getByText('Updated on the original profile',{exact:true}).waitFor();
  assert.deepEqual(failures, []);
  console.log(JSON.stringify({extensionId:id,officialExtensionAlsoLoaded:extensions.length === 2,passed:['separate extension identity and paired account login','annotation-specific reaction persisted','annotation controls exclude page metadata','original annotation save authenticated to cloud API','page metadata/title/tags live in Page Notes','manual and auto tags remain separate','page like and custom group saved independently','Compact library, dashboard and settings','annotation sorting persists','connection failures do not show empty counts','Codex confirmation can be cancelled; offline organization completes','original annotation actions remain available offline','local library lists and searches backed-up pages','local library persists across reload','hosted profile personal title persists'],notes:failures}));
} finally {
  await context.close();
  await fs.rm(profile,{recursive:true,force:true});
}
