/**
 * merge.js — 頁面合併工具
 *
 * 【用途】
 * 將頁面 HTML 與本地 CSS／JS 合併，方便貼進 CMS，或改寫為 jsDelivr CDN
 * 路徑供開發預覽。可點兩下 tools/merge.bat 走選單，或直接用下方 CLI。
 *
 * 【用法】
 *   node merge.js <資料夾路徑> <dev|prod> <body|html>
 *   （prod 亦接受 production／正式）
 *
 * 【輸入規則】
 *   選擇「頁面資料夾」後，只處理該資料夾內與資料夾同名的 HTML：
 *     {folderName}/{folderName}.html
 *   不會處理 *_merge.html；若資料夾名稱以 _merge 結尾會直接拒絕。
 *
 * 【模式 mode】
 *   · 第三方資源：href／src 為 http(s): 或 // 開頭者，一律保留原樣不處理。
 *   · prod：將可解析到的本地相對路徑 CSS／JS 內嵌進輸出
 *       - CSS → <style type="text/css">（內容前註解 repo 相對路徑）
 *       - JS  → <script> 內嵌（去掉 src／defer／async／integrity／crossorigin）
 *   · dev：將本地相對路徑改寫為 jsDelivr：
 *       https://cdn.jsdelivr.net/gh/Pin-Pin-Pin/new-web@{最新tag}/{repo相對路徑}
 *     最新 tag 解析：先嘗試 git fetch new-web --tags；再對
 *     new-web/feature、origin/feature、feature 依序執行
 *     git tag --merged <ref> --sort=-v:refname，取第一個；
 *     皆失敗則退回全部 tag 依版本排序取最新。找不到 tag 則報錯結束。
 *
 * 【輸出範圍 target】
 *   · body：只輸出 <body>…</body>
 *       - body 開頭依 head 原順序放入：
 *         1) preconnect／dns-prefetch 的 <link>
 *         2) 第三方 stylesheet <link>（如 Bootstrap、Google Fonts）
 *         3) 本地 CSS（prod：內嵌 <style>；dev：改寫後的 <link>）
 *       - 腳本集中到 body 末尾：
 *         先 head 內的 script，再原 body 內 script，順序不變
 *         （若原頁有 Bootstrap JS 等第三方 <script src>，會一併以外連方式保留；
 *          本地 JS 依 mode 內嵌或改 CDN）
 *   · html：輸出完整文件
 *       - prod：從 <head> 移除本地 CSS <link>，樣式改放 body 開頭內嵌；
 *               body 內本地 JS 內嵌後仍置於 body 末
 *       - dev：在 <head> 原地改寫本地 CSS／JS 路徑為 CDN；
 *               body 腳本改寫後仍放在 body 末（head 腳本已在 head 改寫）
 *
 * 【輸出檔】
 *   寫回同一資料夾：{basename}_merge.html
 *
 * 【相關】
 *   merge.bat：可點選的選單包裝（選 mode／target、開資料夾選擇器後呼叫本檔）。
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const CDN_OWNER_REPO = 'Pin-Pin-Pin/new-web';
const FEATURE_REFS = ['new-web/feature', 'origin/feature', 'feature'];

function usage() {
  console.error(
    '用法：node merge.js <資料夾路徑> <dev|prod> <body|html>\n' +
      '  dev  = 相對路徑改寫為 jsDelivr（最新 tag）\n' +
      '  prod = 本地 CSS/JS 內嵌\n' +
      '  body = 僅輸出 <body>\n' +
      '  html = 輸出完整 HTML'
  );
}

function isThirdPartyUrl(url) {
  return /^(https?:)?\/\//i.test(String(url || '').trim());
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

/** 僅 body 時要搬進 body 開頭的 head <link>：preconnect／dns-prefetch、第三方 CSS */
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

    if (rel === 'preconnect' || rel === 'dns-prefetch') {
      result.push(tag);
      continue;
    }
    if (rel === 'stylesheet' && href && isThirdPartyUrl(href)) {
      result.push(tag);
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

function rewriteHeadLocalAssets(headContent, htmlDir, repoRoot, tag) {
  let result = headContent.replace(/<link\b[^>]*>/gi, (tagHtml) => {
    if (!/\brel\s*=\s*["']stylesheet["']/i.test(tagHtml)) return tagHtml;
    const hrefMatch = tagHtml.match(/\bhref\s*=\s*["']([^"']+)["']/i);
    if (!hrefMatch || isThirdPartyUrl(hrefMatch[1])) return tagHtml;
    const abs = resolveLocalFile(htmlDir, hrefMatch[1]);
    if (!abs) return tagHtml;
    return replaceAttrValue(tagHtml, 'href', cdnUrl(tag, toRepoRelative(repoRoot, abs)));
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

function collectLocalCss({ links, mode, htmlDir, repoRoot, tag }) {
  const styleParts = [];
  const devLinks = [];

  for (const link of links) {
    if (isThirdPartyUrl(link.href)) continue;

    const abs = resolveLocalFile(htmlDir, link.href);
    if (!abs) {
      console.warn(`⚠️ 找不到本地 CSS，保留原路徑：${link.href}`);
      continue;
    }

    const repoRel = toRepoRelative(repoRoot, abs);
    if (mode === 'dev') {
      devLinks.push(replaceAttrValue(link.tag, 'href', cdnUrl(tag, repoRel)));
    } else {
      styleParts.push(`/* ${repoRel} */\n${fs.readFileSync(abs, 'utf8')}`);
    }
  }

  return { styleParts, devLinks };
}

function buildBodyHtml({ bodyAttrs, bodyContent, headPrefix, scriptsHtml }) {
  const open = bodyAttrs.trim() ? `<body ${bodyAttrs.trim()}>` : '<body>';
  return [open, headPrefix, bodyContent.trim(), scriptsHtml, '</body>']
    .filter((part) => part !== '' && part != null)
    .join('\n');
}

function mergeFile({ folderPath, mode, target }) {
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
    const tagMeta = resolveLatestTag(repoRoot);
    if (!tagMeta) {
      throw new Error(
        '找不到可用的 git tag。請先在 feature 相關 commit 建立並 push tag（例如 v1.1.0）。'
      );
    }
    tag = tagMeta.tag;
    tagVia = tagMeta.via;
  }

  const html = fs.readFileSync(htmlPath, 'utf8');
  const headContent = extractHead(html);
  const body = extractBody(html);
  if (!body) throw new Error('找不到 <body> 區塊');

  const htmlDir = absFolder;
  const links = extractStylesheetLinks(headContent);
  const { styleParts, devLinks } = collectLocalCss({
    links,
    mode,
    htmlDir,
    repoRoot,
    tag,
  });

  const scriptsInHead = extractScriptTags(headContent);
  const scriptsInBody = extractScriptTags(body.content);
  const bodyWithoutScripts = removeScriptTags(body.content).replace(/\n{3,}/g, '\n\n');

  // 僅 body：head + body 的 script 都放到輸出 body 末尾（含 Bootstrap CDN）
  // 完整 HTML：只處理 body 內 script；head 內 script 留在 head
  const scriptsForOutput =
    target === 'body' ? [...scriptsInHead, ...scriptsInBody] : scriptsInBody;

  const scriptsHtml = processScripts({
    scripts: scriptsForOutput,
    mode,
    htmlDir,
    repoRoot,
    tag,
  }).join('\n');

  let output;

  if (target === 'body') {
    const vendorLinks = extractHeadLinksForBody(headContent);
    const localCssPrefix =
      mode === 'prod'
        ? styleParts.length
          ? buildStyleBlock(styleParts)
          : ''
        : devLinks.join('\n');
    const headPrefix = [...vendorLinks, localCssPrefix].filter(Boolean).join('\n');

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
    // dev + 完整 HTML：head 內改寫路徑，body 腳本改寫後仍放在 body 末
    const newHead = rewriteHeadLocalAssets(headContent, htmlDir, repoRoot, tag).trim();
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

  return { outPath, mode, target, tag, tagVia, htmlPath };
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

function main() {
  const folderPath = process.argv[2];
  const mode = normalizeMode(process.argv[3]);
  const target = normalizeTarget(process.argv[4]);

  if (!folderPath || !mode || !target) {
    usage();
    process.exit(1);
  }

  const result = mergeFile({ folderPath, mode, target });
  console.log('✅ 合併完成');
  console.log(`   來源：${result.htmlPath}`);
  console.log(`   輸出：${result.outPath}`);
  console.log(
    `   模式：${result.mode === 'dev' ? 'dev' : '正式'} / ${
      result.target === 'body' ? '僅 body' : '完整 HTML'
    }`
  );
  if (result.tag) {
    console.log(`   CDN tag：${result.tag}${result.tagVia ? `（via ${result.tagVia}）` : ''}`);
  }
}

module.exports = { mergeFile, resolveLatestTag, findRepoRoot };

if (require.main === module) {
  try {
    main();
  } catch (err) {
    console.error(`❌ ${err.message}`);
    process.exit(1);
  }
}
