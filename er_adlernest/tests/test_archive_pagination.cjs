const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '../rootfs/app/frontend/dist/index.html'), 'utf8');
const start = html.indexOf('    const ARCHIVE_PAGE_SIZE =');
const end = html.indexOf('    async function loadHACameras()', start);
assert.ok(start >= 0 && end > start);
const source = html.slice(start, end);

const RECORDINGS_RESP = { ok: true,
  json: async () => ({ total: 101, items: [{ id: 1, camera_name: 'Camera', filename: 'a.mp4', media_type: 'video' }] }) };
const DAYS_RESP = { ok: true, json: async () => ({ days: [] }) };

function autoResp(url) {
  if (url.includes('/days')) return Promise.resolve(DAYS_RESP);
  return Promise.resolve(RECORDINGS_RESP);
}

function setup() {
  const elements = {};
  function element() {
    return { value: '', disabled: false, textContent: '', innerHTML: '', style: {},
      appendChild() {}, append() {}, appendChild() {} };
  }
  const urls = [];
  const responses = [];
  const context = vm.createContext({
    document: {
      getElementById(id) { return elements[id] ||= element(); },
      createElement: element,
      createTextNode(text) { return { textContent: text }; },
    },
    setText(id, text) { (elements[id] ||= element()).textContent = text; },
    console: { error() {} },
    apiFetch(url) {
      urls.push(url);
      if (responses.length) {
        const next = responses[0];
        // Each entry may be { match, response } or a bare Promise/value for recordings
        if (next && typeof next === 'object' && 'match' in next) {
          if (url.includes(next.match)) { responses.shift(); return next.response; }
          return autoResp(url);
        }
        return responses.shift();
      }
      return autoResp(url);
    },
  });
  vm.runInContext(source, context);
  return { context, elements, urls, responses };
}


test('navigates all pages and disables boundary buttons', async () => {
  const { context: c, elements: e, urls } = setup();
  await c.loadRecordings();
  assert.equal(e.archivePrev.disabled, true);
  assert.equal(e.archiveNext.disabled, false);
  await c.changeArchivePage(1);
  await c.changeArchivePage(1);
  const recUrls = urls.filter(u => !u.includes('/days'));
  assert.match(recUrls[2], /limit=50&offset=100/);
  assert.equal(e.archivePageText.textContent, 'Page 3 of 3');
  assert.equal(e.archiveNext.disabled, true);
  const lenBefore = recUrls.length;
  await c.changeArchivePage(1);
  assert.equal(urls.filter(u => !u.includes('/days')).length, lenBefore);
  await c.changeArchivePage(-1);
  assert.match(urls.filter(u => !u.includes('/days'))[3], /offset=50/);
});

test('filter changes reset offset and encode camera names', async () => {
  const { context: c, elements: e, urls } = setup();
  await c.loadRecordings();
  await c.changeArchivePage(1);
  e.filterCamera.value = 'Terrasse & Eingang';
  e.filterEvent.value = 'motion';
  await c.loadRecordings();
  const recUrls = urls.filter(u => !u.includes('/days'));
  assert.match(recUrls[2], /offset=0&camera=Terrasse%20%26%20Eingang&event_type=motion/);
  assert.equal(e.archivePrev.disabled, true);
});

test('stale responses cannot overwrite a newer filter request', async () => {
  const { context: c, elements: e, responses } = setup();
  let resolveOld;
  responses.push(new Promise(resolve => { resolveOld = resolve; }));
  const old = c.loadRecordings(50);
  await c.loadRecordings();
  resolveOld({ ok: true, json: async () => ({ total: 999, items: [] }) });
  await old;
  assert.equal(e.archivePageText.textContent, 'Page 1 of 3');
  assert.equal(e.archiveCountText.textContent, '101 RECORDINGS FOUND');
});

test('failed requests retain the last page and unlock navigation', async () => {
  const { context: c, elements: e, responses } = setup();
  await c.loadRecordings();
  responses.push({ match: 'api/recordings?', response: Promise.resolve({ ok: false }) });
  await c.changeArchivePage(1);
  assert.equal(e.archivePageText.textContent, 'Page 1 of 3');
  assert.equal(e.archiveNext.disabled, false);
  responses.push({ match: 'api/recordings?', response: Promise.reject(new Error('offline')) });
  await c.changeArchivePage(1);
  assert.equal(e.archiveNext.disabled, false);
});
