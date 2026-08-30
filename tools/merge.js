/**
 * merge.js — 頁面合併工具
 *
 * 【用途】
 * 將頁面 HTML 與本地 CSS／JS 合併，方便貼進 CMS，或改寫為 jsDelivr CDN
 * 路徑供開發預覽。可點兩下 merge.bat 走選單，或直接用下方 CLI。
 *
 * 【用法】
 *   node merge.js <dev|prod> <body|html> [tag]
 *   （prod 亦接受 production／正式）
 *   （dev 模式必須提供 tag，例如 v1.1.3）
 *
 * 【輸入規則】
 *   依 target 自動批次處理對應根目錄下「與資料夾同名」的 HTML：
 *     {folderName}/{folderName}.html
 *   · body → new-free-web/ 底下所有頁面資料夾
 *   · html → landing-page/ 底下所有頁面資料夾
 *   不會處理 *_merge.html；若資料夾名稱以 _merge 結尾會略過。
 *
 * 【模式 mode】
 *   · 第三方資源：href／src 為 http(s): 或 // 開頭者，一律保留原樣不處理。
 *   · prod：
 *       - target=html：本地 CSS／JS 內嵌進輸出
 *         CSS → <style type="text/css">；JS → <script> 內嵌
 *       - target=body：本地 CSS／JS 內嵌（貼 CMS）
 *         CSS 依 <link> 原順序插入 <style type="text/css">（*_scoped.css；不存在則報錯）；
 *         本地 JS 內嵌進 <script>（不用 *_scoped）
 *   · dev：將本地相對路徑改寫為 jsDelivr：
 *       https://cdn.jsdelivr.net/gh/Pin-Pin-Pin/new-web@{使用者輸入的tag}/{repo相對路徑}
 *     tag 由 CLI 第 3 參數或 merge.bat 提示輸入；不可省略。
 *   · 不論 mode／target，一律再附上 share-css/fix.css（若頁面尚未引用）：
 *       - html+prod、body+prod → 併入 <style> 末尾
 *       - body+dev → 追加 <link>（接在本地 CSS 後）
 *       - html+dev → 追加 <link>（接在 head 末）
 *   · 本地 CSS 自動改用 scoped 版本（若不存在則報錯）：
 *       - foo.css → foo_scoped.css
 *       - 已是 *_scoped.css 則不改
 *       - 例外：頁面位於 landing-page/ 底下時，一律使用原 CSS（不用 *_scoped.css）
 *       - 例外：merge 自動追加的 share-css/fix.css 維持原檔（無 scoped）
 *       - 本地 JS 不使用 *_scoped
 *
 * 【輸出範圍 target】
 *   · body：只輸出 <body>…</body>（批次 new-free-web）
 *       - 不搬移 preconnect／dns-prefetch（放 body 效益低）
 *       - 不輸出 Bootstrap CSS／JS（假設 CMS 已載入；URL 含 bootstrap 者皆略過）
 *       - Google Fonts Noto Sans TC：CMS 已有 300／400／500，body 輸出只保留其餘字重
 *         （例如原 300;400;500;700 → 只輸出 700，並保留 display=swap；
 *          若無額外字重則整段 <link>／@import 略過）
 *       - 本地 CSS：
 *         prod → 依序內嵌進 <style>（*_scoped.css；不存在則報錯）
 *         dev → 保留為 <link>（*_scoped.css 的 jsDelivr CDN）
 *       - body 開頭依 head 原順序放入：
 *         1) 第三方 stylesheet <link>（如 Google Fonts；不含 Bootstrap）
 *         2) 本地 CSS：prod 為 <style> 內嵌；dev 為 <link>（*_scoped）
 *         3) fix.css：prod 併入同一個 <style> 末尾；dev 為 <link>
 *       - 腳本集中到 body 末尾：
 *         先 head 內的 script，再原 body 內 script，順序不變
 *         （第三方 script 以外連保留，但 Bootstrap JS 略過；
 *          本地 JS 依 mode 內嵌或改 CDN）
 *   · html：輸出完整文件（批次 landing-page）
 *       - prod：從 <head> 移除本地 CSS <link>，樣式改放 body 開頭內嵌；
 *               body 內本地 JS 內嵌後仍置於 body 末
 *       - dev：在 <head> 原地改寫本地 CSS／JS 路徑為 CDN，並於 head 末追加 fix.css；
 *               body 腳本改寫後仍放在 body 末（head 腳本已在 head 改寫）
 *
 * 【輸出檔】
 *   寫回同一資料夾：{basename}_merge.html
 *
 * 【相關】
 *   merge.bat：可點選的選單包裝（選 mode／target／tag 後批次呼叫本檔）。
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const CDN_OWNER_REPO = 'Pin-Pin-Pin/new-web';
const FEATURE_REFS = ['new-web/feature', 'origin/feature', 'feature'];
const FIX_CSS_REPO_REL = 'share-css/fix.css';

/** body／html → repo 相對根目錄 */
const TARGET_ROOTS = {
  body: 'new-free-web',
  html: 'landing-page',
};

function usage() {
  console.error(
    '用法：node merge.js <dev|prod> <body|html> [tag]\n' +
      '  dev  = 相對路徑改寫為 jsDelivr（需提供 tag，例如 v1.1.3）\n' +
      '  prod = 本地 CSS/JS 內嵌（不需 tag）\n' +
      '  body = 僅輸出 <body>，批次處理 new-free-web\n' +
      '  html = 輸出完整 HTML，批次處理 landing-page\n' +
      '  tag  = jsDelivr 使用的 git tag（僅 dev 需要）'
  );
}

function isThirdPartyUrl(url) {
  return /^(https?:)?\/\//i.test(String(url || '').trim());
}

/** Bootstrap CSS／JS（CDN 或路徑含 bootstrap）；body 輸出時略過，避免 CMS 重複載入 */
function isBootstrapAssetUrl(url) {
  return /bootstrap/i.test(String(url || ''));
}

/** CMS 已載入的 Noto Sans TC 字重；body 輸出時略過這些 */
const CMS_NOTO_SANS_TC_WEIGHTS = new Set(['300', '400', '500']);

function isNotoSansTcGoogleFontUrl(url) {
  const u = String(url || '');
  return /fonts\.googleapis\.com/i.test(u) && /Noto[+ ]Sans[+ ]TC/i.test(u);
}

/**
 * 從 Google Fonts css2 URL 取出 Noto Sans TC 的 wght 清單。
 * 例：...Noto+Sans+TC:wght@300;400;500;700&display=swap → ['300','400','500','700']
 */
function parseNotoSansTcWeights(url) {
  const m = String(url || '').match(/Noto\+Sans\+TC:wght@([0-9;]+)/i);
  if (!m) return [];
  return m[1]
    .split(';')
    .map((w) => w.trim())
    .filter(Boolean);
}

/**
 * body 輸出用：只保留 CMS 沒有的字重，並固定 display=swap。
 * @returns {{ action: 'keep'|'omit'|'rewrite', url?: string }}
 */
function rewriteNotoSansTcUrlForBody(url) {
  if (!isNotoSansTcGoogleFontUrl(url)) return { action: 'keep', url };
  const weights = parseNotoSansTcWeights(url);
  const extra = weights.filter((w) => !CMS_NOTO_SANS_TC_WEIGHTS.has(w));
  if (extra.length === 0) return { action: 'omit' };
  return {
    action: 'rewrite',
    url: `https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@${extra.join(';')}&display=swap`,
  };
}

/** 改寫／略過 <link> 上的 Noto Sans TC（body 用） */
function rewriteNotoSansTcLinkTagForBody(tag) {
  const hrefMatch = tag.match(/\bhref\s*=\s*["']([^"']+)["']/i);
  if (!hrefMatch) return tag;
  const result = rewriteNotoSansTcUrlForBody(hrefMatch[1]);
  if (result.action === 'omit') return '';
  if (result.action === 'rewrite') return replaceAttrValue(tag, 'href', result.url);
  return tag;
}

/**
 * 改寫 CSS 內 @import 的 Noto Sans TC（body 用）。
 * 無額外字重則刪除該 @import；有則改寫 URL 並保留 display=swap。
 */
function rewriteNotoSansTcImportsInCssForBody(css) {
  return String(css || '').replace(
    /@import\s+(?:url\s*\(\s*)?(['"]?)([^'")\s]+)\1\s*\)?\s*;?/gi,
    (full, _quote, url) => {
      if (!isNotoSansTcGoogleFontUrl(url)) return full;
      const result = rewriteNotoSansTcUrlForBody(url);
      if (result.action === 'omit') return '';
      if (result.action === 'rewrite') return `@import url('${result.url}');`;
      return full;
    }
  );
}

function findRepoRoot(startDir) {
  let dir = path.resolve(startDir);
  while (true) {
    if (fs.existsSync(path.join(dir, '.git'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function runGit(repoRoot, args) {
  try {
    return execFileSync('git', ['-C', repoRoot, ...args], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
  } catch (err) {
    const stderr = err.stderr ? String(err.stderr).trim() : '';
    throw new Error(stderr || err.message);
  }
}

function resolveLatestTag(repoRoot) {
  try {
    runGit(repoRoot, ['fetch', 'new-web', '--tags', '--quiet']);
  } catch (_) {
    // 離線時略過
  }

  for (const ref of FEATURE_REFS) {
    try {
      const out = runGit(repoRoot, ['tag', '--merged', ref, '--sort=-v:refname']);
      const tag = out
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean)[0];
      if (tag) return { tag, via: ref };
    } catch (_) {
      // 試下一個 ref
    }
  }

  try {
    const out = runGit(repoRoot, ['tag', '--sort=-v:refname']);
    const tag = out
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean)[0];
    if (tag) return { tag, via: 'all-tags' };
  } catch (_) {
    // ignore
  }

  return null;
}

function toPosix(p) {
  return p.split(path.sep).join('/');
}

function stripUrlDecorations(url) {
  return String(url).split('#')[0].split('?')[0];
}

function resolveLocalFile(htmlDir, url) {
  const cleaned = stripUrlDecorations(url);
  if (!cleaned || isThirdPartyUrl(cleaned) || cleaned.startsWith('/')) return null;
  const abs = path.resolve(htmlDir, cleaned);
  if (!fs.existsSync(abs) || !fs.statSync(abs).isFile()) return null;
  return abs;
}

function toRepoRelative(repoRoot, absFile) {
  const rel = path.relative(repoRoot, absFile);
  if (rel.startsWith('..') || path.isAbsolute(rel)) {
    throw new Error(`檔案不在 repo 內：${absFile}`);
  }
  return toPosix(rel);
}

function cdnUrl(tag, repoRelativePath) {
  return `https://cdn.jsdelivr.net/gh/${CDN_OWNER_REPO}@${tag}/${repoRelativePath}`;
}

function extractHead(html) {
  const match = html.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
  return match ? match[1] : '';
}

function extractBody(html) {
  const match = html.match(/<body([^>]*)>([\s\S]*?)<\/body>/i);
  if (!match) return null;
  return { attrs: match[1] || '', content: match[2] };
}

function extractStylesheetLinks(headContent) {
  const links = [];
  const regex = /<link\b[^>]*>/gi;
  let match;
  while ((match = regex.exec(headContent)) !== null) {
    const tag = match[0];
    if (!/\brel\s*=\s*["']stylesheet["']/i.test(tag)) continue;
    const hrefMatch = tag.match(/\bhref\s*=\s*["']([^"']+)["']/i);
    if (!hrefMatch) continue;
    links.push({ tag, href: hrefMatch[1] });
  }
  return links;
}

/**
 * 僅 body 時要搬進 body 開頭的 head <link>：第三方 CSS
 * （不含 preconnect／dns-prefetch，也不含 Bootstrap；
 *  Noto Sans TC 只保留 CMS 以外字重，無額外字重則略過）
 */
function extractHeadLinksForBody(headContent) {
  const result = [];
  const regex = /<link\b[^>]*>/gi;
  let match;
  while ((match = regex.exec(headContent)) !== null) {
    const tag = match[0];
    const relMatch = tag.match(/\brel\s*=\s*["']([^"']+)["']/i);
    const rel = relMatch ? relMatch[1].toLowerCase() : '';
    const hrefMatch = tag.match(/\bhref\s*=\s*["']([^"']+)["']/i);
    const href = hrefMatch ? hrefMatch[1] : '';

    if (
      rel === 'stylesheet' &&
      href &&
      isThirdPartyUrl(href) &&
      !isBootstrapAssetUrl(href)
    ) {
      const rewritten = rewriteNotoSansTcLinkTagForBody(tag);
      if (rewritten) result.push(rewritten);
    }
  }
  return result;
}

function extractScriptTags(htmlFragment) {
  const scripts = [];
  const regex = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let match;
  while ((match = regex.exec(htmlFragment)) !== null) {
    scripts.push({
      full: match[0],
      attrs: match[1] || '',
      src: (match[1].match(/\bsrc\s*=\s*["']([^"']+)["']/i) || [])[1] || null,
    });
  }
  return scripts;
}

function replaceAttrValue(tag, attrName, newValue) {
  const re = new RegExp(`(\\b${attrName}\\s*=\\s*)(["'])([^"']*)(\\2)`, 'i');
  if (re.test(tag)) return tag.replace(re, `$1$2${newValue}$4`);
  return tag;
}

function fixDevScriptTag(fullTag, newSrc) {
  const openEnd = fullTag.indexOf('>');
  if (openEnd === -1) return fullTag;
  const openTag = fullTag.slice(0, openEnd + 1);
  const rest = fullTag.slice(openEnd + 1);
  return replaceAttrValue(openTag, 'src', newSrc) + rest;
}

function removeLocalStylesheetLinks(headContent, htmlDir) {
  return headContent.replace(/<link\b[^>]*>/gi, (tag) => {
    if (!/\brel\s*=\s*["']stylesheet["']/i.test(tag)) return tag;
    const hrefMatch = tag.match(/\bhref\s*=\s*["']([^"']+)["']/i);
    if (!hrefMatch || isThirdPartyUrl(hrefMatch[1])) return tag;
    return resolveLocalFile(htmlDir, hrefMatch[1]) ? '' : tag;
  });
}

/** 頁面資料夾是否在 landing-page/ 底下（此區不用 scoped CSS） */
function isLandingPageFolder(absFolder, repoRoot) {
  const rel = toPosix(path.relative(repoRoot, absFolder));
  if (!rel || rel.startsWith('..')) return false;
  return rel === 'landing-page' || rel.startsWith('landing-page/');
}

/**
 * 本地 CSS → *_scoped.css。
 * 已是 *_scoped.css、或 useScoped=false（landing-page）則原樣回傳；找不到則報錯。
 */
function resolveMergeCssPath(absCssPath, _pageBasename, useScoped = true) {
  const ext = path.extname(absCssPath);
  if (ext.toLowerCase() !== '.css' || !useScoped) return absCssPath;

  const dir = path.dirname(absCssPath);
  const base = path.basename(absCssPath, ext);
  if (/_scoped$/i.test(base)) return absCssPath;

  const scopedAbs = path.join(dir, `${base}_scoped${ext}`);
  if (!fs.existsSync(scopedAbs) || !fs.statSync(scopedAbs).isFile()) {
    throw new Error(
      `找不到 scoped CSS：${scopedAbs}\n` +
        `請先對對應的 CSS 執行「CSS加上main-content.bat」（scope-css）產生 *_scoped.css。`
    );
  }
  return scopedAbs;
}

function rewriteHeadLocalAssets(headContent, htmlDir, repoRoot, tag, pageBasename, useScoped) {
  let result = headContent.replace(/<link\b[^>]*>/gi, (tagHtml) => {
    if (!/\brel\s*=\s*["']stylesheet["']/i.test(tagHtml)) return tagHtml;
    const hrefMatch = tagHtml.match(/\bhref\s*=\s*["']([^"']+)["']/i);
    if (!hrefMatch || isThirdPartyUrl(hrefMatch[1])) return tagHtml;
    const abs = resolveLocalFile(htmlDir, hrefMatch[1]);
    if (!abs) return tagHtml;
    const useAbs = resolveMergeCssPath(abs, pageBasename, useScoped);
    return replaceAttrValue(tagHtml, 'href', cdnUrl(tag, toRepoRelative(repoRoot, useAbs)));
  });

  result = result.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, (full) => {
    const srcMatch = full.match(/\bsrc\s*=\s*["']([^"']+)["']/i);
    if (!srcMatch || isThirdPartyUrl(srcMatch[1])) return full;
    const abs = resolveLocalFile(htmlDir, srcMatch[1]);
    if (!abs) return full;
    return fixDevScriptTag(full, cdnUrl(tag, toRepoRelative(repoRoot, abs)));
  });

  return result;
}

function removeScriptTags(fragment) {
  return fragment.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '');
}

function buildStyleBlock(cssParts) {
  return `<style type="text/css">\n${cssParts.filter(Boolean).join('\n\n')}\n</style>`;
}

function buildInlineScript(originalAttrs, code) {
  const attrs = originalAttrs
    .replace(/\bsrc\s*=\s*["'][^"']*["']/i, '')
    .replace(/\bdefer\b/gi, '')
    .replace(/\basync\b/gi, '')
    .replace(/\bintegrity\s*=\s*["'][^"']*["']/i, '')
    .replace(/\bcrossorigin\s*=\s*["'][^"']*["']/i, '')
    .replace(/\s+/g, ' ')
    .trim();
  return `<script${attrs ? ` ${attrs}` : ''}>\n${code}\n</script>`;
}

function processScripts({ scripts, mode, htmlDir, repoRoot, tag }) {
  return scripts.map((script) => {
    if (!script.src) return script.full;
    if (isThirdPartyUrl(script.src)) return script.full;

    const abs = resolveLocalFile(htmlDir, script.src);
    if (!abs) {
      console.warn(`⚠️ 找不到本地 JS，保留原路徑：${script.src}`);
      return script.full;
    }

    if (mode === 'dev') {
      return fixDevScriptTag(script.full, cdnUrl(tag, toRepoRelative(repoRoot, abs)));
    }

    return buildInlineScript(script.attrs, fs.readFileSync(abs, 'utf8'));
  });
}

function collectLocalCss({
  links,
  mode,
  htmlDir,
  repoRoot,
  tag,
  pageBasename,
  useScoped,
  asLinks = false,
}) {
  const styleParts = [];
  const cssLinks = [];

  for (const link of links) {
    if (isThirdPartyUrl(link.href)) continue;

    const abs = resolveLocalFile(htmlDir, link.href);
    if (!abs) {
      console.warn(`⚠️ 找不到本地 CSS，保留原路徑：${link.href}`);
      continue;
    }

    const useAbs = resolveMergeCssPath(abs, pageBasename, useScoped);
    const repoRel = toRepoRelative(repoRoot, useAbs);
    if (asLinks || mode === 'dev') {
      const href =
        mode === 'dev' ? cdnUrl(tag, repoRel) : toPosix(path.relative(htmlDir, useAbs));
      cssLinks.push(replaceAttrValue(link.tag, 'href', href));
    } else {
      styleParts.push(`/* ${repoRel} */\n${fs.readFileSync(useAbs, 'utf8')}`);
    }
  }

  return { styleParts, cssLinks };
}

function resolveFixCssPath(repoRoot) {
  const abs = path.join(repoRoot, ...FIX_CSS_REPO_REL.split('/'));
  if (!fs.existsSync(abs) || !fs.statSync(abs).isFile()) {
    throw new Error(`找不到 ${FIX_CSS_REPO_REL}`);
  }
  return abs;
}

function pageAlreadyHasFixCss(links, htmlDir, fixAbs) {
  const fixResolved = path.resolve(fixAbs);
  return links.some((link) => {
    if (/share-css\/fix\.css(?:[?#]|$)/i.test(link.href)) return true;
    if (isThirdPartyUrl(link.href)) return false;
    const abs = resolveLocalFile(htmlDir, link.href);
    return abs ? path.resolve(abs) === fixResolved : false;
  });
}

/**
 * 取得要追加的 fix.css（內嵌 style 片段或 <link>）。
 * 若頁面已引用則回傳空字串，避免重複。
 * asLink=true（body）或 mode=dev → 一律用 <link>。
 */
function buildFixCssExtra({ mode, repoRoot, tag, links, htmlDir, asLink = false }) {
  const fixAbs = resolveFixCssPath(repoRoot);
  if (pageAlreadyHasFixCss(links, htmlDir, fixAbs)) {
    return { stylePart: '', linkHtml: '', skipped: true };
  }
  const repoRel = toRepoRelative(repoRoot, fixAbs);
  if (asLink || mode === 'dev') {
    const href =
      mode === 'dev' ? cdnUrl(tag, repoRel) : toPosix(path.relative(htmlDir, fixAbs));
    return {
      stylePart: '',
      linkHtml: `<link rel="stylesheet" href="${href}">`,
      skipped: false,
    };
  }
  return {
    stylePart: `/* ${repoRel} */\n${fs.readFileSync(fixAbs, 'utf8')}`,
    linkHtml: '',
    skipped: false,
  };
}

function buildBodyHtml({ bodyAttrs, bodyContent, headPrefix, scriptsHtml }) {
  const open = bodyAttrs.trim() ? `<body ${bodyAttrs.trim()}>` : '<body>';
  return [open, headPrefix, bodyContent.trim(), scriptsHtml, '</body>']
    .filter((part) => part !== '' && part != null)
    .join('\n');
}

function normalizeTag(input) {
  let tag = String(input || '').trim();
  if (tag.startsWith('@')) tag = tag.slice(1);
  return tag;
}

/**
 * 收集 target 對應根目錄下可 merge 的頁面資料夾
 *（直接子資料夾，且存在 {name}/{name}.html）
 */
function discoverPageFolders(repoRoot, target) {
  const relRoot = TARGET_ROOTS[target];
  if (!relRoot) throw new Error(`未知 target：${target}`);

  const absRoot = path.join(repoRoot, ...relRoot.split('/'));
  if (!fs.existsSync(absRoot) || !fs.statSync(absRoot).isDirectory()) {
    throw new Error(`找不到資料夾：${absRoot}`);
  }

  const folders = [];
  for (const ent of fs.readdirSync(absRoot, { withFileTypes: true })) {
    if (!ent.isDirectory()) continue;
    if (/_merge$/i.test(ent.name)) continue;
    const absFolder = path.join(absRoot, ent.name);
    const htmlPath = path.join(absFolder, `${ent.name}.html`);
    if (!fs.existsSync(htmlPath) || !fs.statSync(htmlPath).isFile()) continue;
    folders.push(absFolder);
  }

  folders.sort((a, b) => a.localeCompare(b));
  if (folders.length === 0) {
    throw new Error(`在 ${relRoot}/ 底下找不到可合併的頁面資料夾`);
  }
  return { relRoot, absRoot, folders };
}

function mergeFile({ folderPath, mode, target, tag: tagInput }) {
  const absFolder = path.resolve(folderPath);
  if (!fs.existsSync(absFolder) || !fs.statSync(absFolder).isDirectory()) {
    throw new Error(`資料夾不存在：${absFolder}`);
  }

  const basename = path.basename(absFolder);
  if (/_merge$/i.test(basename)) {
    throw new Error('請選擇原始頁面資料夾，不要選擇 merge 輸出相關名稱');
  }

  const htmlPath = path.join(absFolder, `${basename}.html`);
  if (!fs.existsSync(htmlPath)) {
    throw new Error(
      `找不到與資料夾同名的 HTML：${htmlPath}\n` +
        `請選擇實際頁面資料夾（例如 landing-page\\general-donate），不要選專案根目錄。`
    );
  }

  const repoRoot = findRepoRoot(absFolder) || findRepoRoot(__dirname);
  if (!repoRoot) throw new Error('找不到 git repo 根目錄');

  let tag = null;
  let tagVia = null;
  if (mode === 'dev') {
    tag = normalizeTag(tagInput);
    if (!tag) {
      throw new Error('dev 模式請提供 git tag（例如 v1.1.3）');
    }
    tagVia = 'user';
  }

  const html = fs.readFileSync(htmlPath, 'utf8');
  const headContent = extractHead(html);
  const body = extractBody(html);
  if (!body) throw new Error('找不到 <body> 區塊');

  const htmlDir = absFolder;
  const useScoped = !isLandingPageFolder(absFolder, repoRoot);
  // body+dev：本地 CSS 仍用 <link>（CDN）；body+prod／html+prod：內嵌進 <style>
  const keepCssAsLinks = target === 'body' && mode === 'dev';
  const links = extractStylesheetLinks(headContent);
  const { styleParts, cssLinks } = collectLocalCss({
    links,
    mode,
    htmlDir,
    repoRoot,
    tag,
    pageBasename: basename,
    useScoped,
    asLinks: keepCssAsLinks,
  });

  const fixCss = buildFixCssExtra({
    mode,
    repoRoot,
    tag,
    links,
    htmlDir,
    asLink: keepCssAsLinks,
  });
  // body+dev：CSS／fix 用 <link>；body+prod／html+prod：fix 併入 style；html+dev：fix 追加 link
  if (target === 'body' || mode === 'prod') {
    if (fixCss.stylePart) styleParts.push(fixCss.stylePart);
    if (fixCss.linkHtml) cssLinks.push(fixCss.linkHtml);
  }

  const scriptsInHead = extractScriptTags(headContent);
  const scriptsInBody = extractScriptTags(body.content);
  let bodyWithoutScripts = removeScriptTags(body.content).replace(/\n{3,}/g, '\n\n');

  // 僅 body：head + body 的 script 都放到輸出 body 末尾（不含 Bootstrap CDN）
  // 完整 HTML：只處理 body 內 script；head 內 script 留在 head
  let scriptsForOutput =
    target === 'body' ? [...scriptsInHead, ...scriptsInBody] : scriptsInBody;
  if (target === 'body') {
    scriptsForOutput = scriptsForOutput.filter(
      (script) => !script.src || !isBootstrapAssetUrl(script.src)
    );
  }

  const scriptsHtml = processScripts({
    scripts: scriptsForOutput,
    mode,
    htmlDir,
    repoRoot,
    tag,
  }).join('\n');

  let output;

  if (target === 'body') {
    // body：頁內／內嵌 CSS 的 Noto @import 也只保留額外字重
    bodyWithoutScripts = rewriteNotoSansTcImportsInCssForBody(bodyWithoutScripts);
    const inlinedStyleParts = styleParts.map(rewriteNotoSansTcImportsInCssForBody);

    const vendorLinks = extractHeadLinksForBody(headContent);
    const headPrefix = [
      ...vendorLinks,
      inlinedStyleParts.length ? buildStyleBlock(inlinedStyleParts) : '',
      ...cssLinks,
    ]
      .filter(Boolean)
      .join('\n');

    output = buildBodyHtml({
      bodyAttrs: body.attrs,
      bodyContent: bodyWithoutScripts,
      headPrefix,
      scriptsHtml,
    });
  } else if (mode === 'prod') {
    const newHead = removeLocalStylesheetLinks(headContent, htmlDir).trim();
    const newBody = buildBodyHtml({
      bodyAttrs: body.attrs,
      bodyContent: bodyWithoutScripts,
      headPrefix: styleParts.length ? buildStyleBlock(styleParts) : '',
      scriptsHtml,
    });
    output = html
      .replace(/<head[^>]*>[\s\S]*?<\/head>/i, `<head>\n${newHead}\n</head>`)
      .replace(/<body[^>]*>[\s\S]*?<\/body>/i, newBody);
  } else {
    // dev + 完整 HTML：head 內改寫路徑，並於 head 末追加 fix.css link
    let newHead = rewriteHeadLocalAssets(
      headContent,
      htmlDir,
      repoRoot,
      tag,
      basename,
      useScoped
    ).trim();
    if (fixCss.linkHtml) {
      newHead = `${newHead}\n${fixCss.linkHtml}`;
    }
    const newBody = buildBodyHtml({
      bodyAttrs: body.attrs,
      bodyContent: bodyWithoutScripts,
      headPrefix: '',
      scriptsHtml,
    });
    output = html
      .replace(/<head[^>]*>[\s\S]*?<\/head>/i, `<head>\n${newHead}\n</head>`)
      .replace(/<body[^>]*>[\s\S]*?<\/body>/i, newBody);
  }

  const outPath = path.join(absFolder, `${basename}_merge.html`);
  fs.writeFileSync(outPath, `${output.trim()}\n`, 'utf8');

  return {
    outPath,
    mode,
    target,
    tag,
    tagVia,
    htmlPath,
    fixCss: fixCss.skipped ? 'already-linked' : FIX_CSS_REPO_REL,
    useScoped,
  };
}

function normalizeMode(input) {
  const v = String(input || '').trim().toLowerCase();
  if (v === 'dev') return 'dev';
  if (v === 'prod' || v === 'production' || v === '正式') return 'prod';
  return null;
}

function normalizeTarget(input) {
  const v = String(input || '').trim().toLowerCase();
  if (v === 'body') return 'body';
  if (v === 'html') return 'html';
  return null;
}

function printMergeResult(result) {
  console.log('✅ 合併完成');
  console.log(`   來源：${result.htmlPath}`);
  console.log(`   輸出：${result.outPath}`);
  console.log(
    `   模式：${result.mode === 'dev' ? 'dev' : '正式'} / ${
      result.target === 'body' ? '僅 body' : '完整 HTML'
    }`
  );
  if (result.tag) {
    console.log(`   CDN tag：${result.tag}`);
  }
  if (result.fixCss) {
    console.log(
      `   fix.css：${
        result.fixCss === 'already-linked' ? '頁面已引用，略過追加' : `已追加 ${result.fixCss}`
      }`
    );
  }
  if (result.useScoped === false) {
    console.log('   scoped CSS：landing-page，使用原 CSS');
  }
}

function main() {
  const mode = normalizeMode(process.argv[2]);
  const target = normalizeTarget(process.argv[3]);
  const tag = process.argv[4];

  if (!mode || !target) {
    usage();
    process.exit(1);
  }

  if (mode === 'dev' && !normalizeTag(tag)) {
    usage();
    console.error('❌ dev 模式必須提供 tag（第 3 個參數），例如：v1.1.3');
    process.exit(1);
  }

  const repoRoot = findRepoRoot(__dirname) || findRepoRoot(process.cwd());
  if (!repoRoot) throw new Error('找不到 git repo 根目錄');

  const { relRoot, folders } = discoverPageFolders(repoRoot, target);
  console.log(
    `批次合併：${target === 'body' ? '僅 body' : '完整 HTML'} → ${relRoot}/（${folders.length} 個）`
  );
  console.log('');

  const ok = [];
  const failed = [];
  for (const folderPath of folders) {
    try {
      const result = mergeFile({ folderPath, mode, target, tag });
      printMergeResult(result);
      ok.push(result);
      console.log('');
    } catch (err) {
      console.error(`❌ ${folderPath}`);
      console.error(`   ${err.message}`);
      console.log('');
      failed.push({ folderPath, message: err.message });
    }
  }

  console.log('————————');
  console.log(`成功：${ok.length} ／ 失敗：${failed.length}`);
  if (failed.length) {
    process.exit(1);
  }
}

module.exports = {
  mergeFile,
  discoverPageFolders,
  resolveLatestTag,
  findRepoRoot,
  normalizeTag,
  resolveMergeCssPath,
  TARGET_ROOTS,
};

if (require.main === module) {
  try {
    main();
  } catch (err) {
    console.error(`❌ ${err.message}`);
    process.exit(1);
  }
}
