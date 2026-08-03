/**
 * scope-css.js — 為 CSS 選擇器加上 #main 前綴
 *
 * 【用途】
 * 將選定 CSS 的規則選擇器前面加上 #main（CMS 主內容區 id），
 * 避免樣式影響 footer 等其他區塊。
 * 若選擇器開頭已有 #main 則略過。
 * 若開頭是舊前綴 #main-content，會改寫成 #main。
 *
 * 【用法】
 *   node scope-css.js <css檔路徑>
 *
 * 【規則】
 *   · .foo, .bar  →  #main .foo, #main .bar
 *   · @media / @supports / @layer 區塊內的規則一併處理
 *   · @keyframes / @font-face / @property 整段保留不改
 *   · :root 不加上前綴（CSS 變數需掛在文件根）
 *   · 輸出：同資料夾 {原檔名}_scoped.css（不覆寫原檔）
 */

const fs = require('fs');
const path = require('path');

const PREFIX = '#main';
const LEGACY_PREFIX = '#main-content';

function usage() {
  console.error('用法：node scope-css.js <css檔路徑>');
}

function startsWithPrefixToken(selector, prefix) {
  const s = selector.trim();
  if (!s) return false;
  if (s === prefix) return true;
  if (s.startsWith(`${prefix} `)) return true;
  if (
    s.startsWith(`${prefix}.`) ||
    s.startsWith(`${prefix}#`) ||
    s.startsWith(`${prefix}[`) ||
    s.startsWith(`${prefix}:`) ||
    s.startsWith(`${prefix}>`) ||
    s.startsWith(`${prefix}+`) ||
    s.startsWith(`${prefix}~`)
  ) {
    return true;
  }
  return false;
}

function alreadyPrefixed(selector) {
  return startsWithPrefixToken(selector, PREFIX);
}

/** 舊工具曾用 #main-content；CMS 實際 id 為 #main */
function rewriteLegacyPrefix(selector) {
  const s = selector.trim();
  if (!startsWithPrefixToken(s, LEGACY_PREFIX)) return null;
  return PREFIX + s.slice(LEGACY_PREFIX.length);
}

function shouldSkipSelector(selector) {
  const s = selector.trim();
  if (!s) return true;
  // CSS 變數掛在 :root，加上前綴會失效
  if (s === ':root' || s.startsWith(':root')) return true;
  return false;
}

function prefixSelectorList(selectorText) {
  const parts = [];
  let current = '';
  let depth = 0; // () for :not(), :is(), etc.
  let inStr = null;

  for (let i = 0; i < selectorText.length; i++) {
    const ch = selectorText[i];
    if (inStr) {
      current += ch;
      if (ch === inStr && selectorText[i - 1] !== '\\') inStr = null;
      continue;
    }
    if (ch === '"' || ch === "'") {
      inStr = ch;
      current += ch;
      continue;
    }
    if (ch === '(') {
      depth++;
      current += ch;
      continue;
    }
    if (ch === ')') {
      depth = Math.max(0, depth - 1);
      current += ch;
      continue;
    }
    if (ch === ',' && depth === 0) {
      parts.push(current);
      current = '';
      continue;
    }
    current += ch;
  }
  if (current.trim() || parts.length === 0) parts.push(current);

  return parts
    .map((part) => {
      const leading = part.match(/^\s*/)?.[0] ?? '';
      const trailing = part.match(/\s*$/)?.[0] ?? '';
      const core = part.trim();
      if (!core) return part;
      if (shouldSkipSelector(core)) return part;
      const legacy = rewriteLegacyPrefix(core);
      if (legacy != null) return `${leading}${legacy}${trailing}`;
      if (alreadyPrefixed(core)) return part;
      return `${leading}${PREFIX} ${core}${trailing}`;
    })
    .join(',');
}

/** 略過不應改寫內部選擇器的 at-rule */
function isPassthroughAtRule(atName) {
  return /^(keyframes|font-face|property|counter-style|font-feature-values|page|color-profile|-webkit-keyframes|-moz-keyframes)$/i.test(
    atName
  );
}

/** 應遞迴進區塊、並前綴內部規則的 at-rule */
function isNestingAtRule(atName) {
  return /^(media|supports|layer|container|document|-moz-document)$/i.test(atName);
}

function skipComment(css, i) {
  if (css.startsWith('/*', i)) {
    const end = css.indexOf('*/', i + 2);
    if (end === -1) return { end: css.length, text: css.slice(i) };
    return { end: end + 2, text: css.slice(i, end + 2) };
  }
  return null;
}

function findMatchingBrace(css, openIndex) {
  let depth = 0;
  let inStr = null;
  for (let i = openIndex; i < css.length; i++) {
    const comment = skipComment(css, i);
    if (comment && !inStr) {
      i = comment.end - 1;
      continue;
    }
    const ch = css[i];
    if (inStr) {
      if (ch === inStr && css[i - 1] !== '\\') inStr = null;
      continue;
    }
    if (ch === '"' || ch === "'") {
      inStr = ch;
      continue;
    }
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/**
 * @param {string} css
 * @param {'root'|'style'} parentKind root=頂層或 media 等；style=已在一般規則內（巢狀 CSS 不再加前綴）
 */
function transformBlock(css, parentKind) {
  let i = 0;
  let out = '';

  while (i < css.length) {
    const comment = skipComment(css, i);
    if (comment) {
      out += comment.text;
      i = comment.end;
      continue;
    }

    if (/\s/.test(css[i])) {
      out += css[i];
      i++;
      continue;
    }

    // 找下一個 { 或 ;
    let j = i;
    let inStr = null;
    let prelude = '';
    while (j < css.length) {
      const c = skipComment(css, j);
      if (c && !inStr) {
        prelude += c.text;
        j = c.end;
        continue;
      }
      const ch = css[j];
      if (inStr) {
        prelude += ch;
        if (ch === inStr && css[j - 1] !== '\\') inStr = null;
        j++;
        continue;
      }
      if (ch === '"' || ch === "'") {
        inStr = ch;
        prelude += ch;
        j++;
        continue;
      }
      if (ch === '{' || ch === ';') break;
      prelude += ch;
      j++;
    }

    if (j >= css.length) {
      out += css.slice(i);
      break;
    }

    if (css[j] === ';') {
      out += css.slice(i, j + 1);
      i = j + 1;
      continue;
    }

    // css[j] === '{'
    const close = findMatchingBrace(css, j);
    if (close === -1) {
      out += css.slice(i);
      break;
    }

    const inner = css.slice(j + 1, close);
    const head = prelude.trim();
    const headRaw = css.slice(i, j); // 含空白／註解的 prelude

    if (head.startsWith('@')) {
      const atMatch = head.match(/^@([a-zA-Z_-]+)/);
      const atName = atMatch ? atMatch[1] : '';

      if (isPassthroughAtRule(atName)) {
        out += css.slice(i, close + 1);
      } else if (isNestingAtRule(atName)) {
        out += headRaw + '{' + transformBlock(inner, 'root') + '}';
      } else {
        // 其他 at-rule：保守整段保留
        out += css.slice(i, close + 1);
      }
    } else if (parentKind === 'root') {
      const prefixed = prefixSelectorList(headRaw);
      out += prefixed + '{' + transformBlock(inner, 'style') + '}';
    } else {
      // 已在一般規則內的巢狀選擇器：不再加前綴
      out += css.slice(i, close + 1);
    }

    i = close + 1;
  }

  return out;
}

function scopeCssFile(cssPath) {
  const abs = path.resolve(cssPath);
  if (!fs.existsSync(abs) || !fs.statSync(abs).isFile()) {
    throw new Error(`找不到 CSS 檔：${abs}`);
  }
  if (path.extname(abs).toLowerCase() !== '.css') {
    throw new Error(`請選擇 .css 檔：${abs}`);
  }

  const input = fs.readFileSync(abs, 'utf8');
  const output = transformBlock(input, 'root');

  const dir = path.dirname(abs);
  const base = path.basename(abs, path.extname(abs));
  const outPath = path.join(dir, `${base}_scoped.css`);
  fs.writeFileSync(outPath, output, 'utf8');

  return { inPath: abs, outPath };
}

function main() {
  const cssPath = process.argv[2];
  if (!cssPath) {
    usage();
    process.exit(1);
  }
  const result = scopeCssFile(cssPath);
  console.log('✅ 完成');
  console.log(`   來源：${result.inPath}`);
  console.log(`   輸出：${result.outPath}`);
  console.log(`   前綴：${PREFIX}`);
}

module.exports = { scopeCssFile, prefixSelectorList, transformBlock, PREFIX };

if (require.main === module) {
  try {
    main();
  } catch (err) {
    console.error(`❌ ${err.message}`);
    process.exit(1);
  }
}
