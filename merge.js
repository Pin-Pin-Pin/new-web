const fs = require('fs');
const readline = require('readline');

function normalizeBasename(input) {
  const trimmed = input.trim();
  if (!trimmed) return null;
  const base = trimmed.replace(/\.html$/i, '');
  if (!/^[a-zA-Z0-9_-]+$/.test(base)) {
    return null;
  }
  return base;
}

function normalizeTarget(input) {
  const target = input.trim().toLowerCase();
  if (target === 'body' || target === 'html') return target;
  return null;
}

function ask(question) {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer);
    });
  });
}

function extractHead(html) {
  const match = html.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
  return match ? match[1] : '';
}

function extractBodyContent(html) {
  const htmlWithoutHead = html.replace(/<head[^>]*>[\s\S]*?<\/head>/gi, '');
  const bodyMatch = htmlWithoutHead.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
  if (!bodyMatch) return null;
  return bodyMatch[1].trim();
}

function extractStylesheetLinks(headContent) {
  const links = [];
  const regex = /<link[^>]*>/gi;
  let match;
  while ((match = regex.exec(headContent)) !== null) {
    const tag = match[0];
    if (!/rel\s*=\s*["']stylesheet["']/i.test(tag)) continue;
    const hrefMatch = tag.match(/href\s*=\s*["']([^"']+)["']/i);
    if (hrefMatch) links.push({ tag, href: hrefMatch[1] });
  }
  return links;
}

function isLocalMergedCss(href, basename) {
  const filename = href.split('?')[0].split('#')[0].replace(/^\.\//, '').split('/').pop();
  return filename === 'share.css' || filename === `${basename}.css`;
}

function toCssImport(href) {
  return `@import url(${JSON.stringify(href)});`;
}

function buildMetaComments(html) {
  const metaMatches = [...html.matchAll(/<meta[^>]*>/gi)];
  return metaMatches
    .map((m) => `<!-- ${m[0].replace(/</g, '').replace(/>/g, '').trim()} -->`)
    .join('\n');
}

function removeLocalCssLinks(headContent, basename) {
  return headContent.replace(/<link[^>]*>/gi, (tag) => {
    if (!/rel\s*=\s*["']stylesheet["']/i.test(tag)) return tag;
    const hrefMatch = tag.match(/href\s*=\s*["']([^"']+)["']/i);
    if (!hrefMatch) return tag;
    return isLocalMergedCss(hrefMatch[1], basename) ? '' : tag;
  });
}

function buildBodyModeOutput({ html, basename, shareCss, pageCss }) {
  const headContent = extractHead(html);
  const bodyContent = extractBodyContent(html);
  if (!bodyContent) {
    throw new Error('找不到 <body> 區塊');
  }

  const externalLinks = extractStylesheetLinks(headContent).filter(
    (link) => !isLocalMergedCss(link.href, basename)
  );

  const importRules = externalLinks.map((link) => toCssImport(link.href)).join('\n');
  const styleParts = [importRules, shareCss, pageCss].filter(Boolean);
  const inlineCSS = `<style>\n${styleParts.join('\n')}\n</style>`;
  const metaComments = buildMetaComments(html);
  return `${inlineCSS}\n${metaComments}\n<body>\n${bodyContent}\n</body>`;
}

function buildHtmlModeOutput({ html, basename, shareCss, pageCss }) {
  const headContent = extractHead(html);
  if (!headContent) {
    throw new Error('找不到 <head> 區塊');
  }

  const cleanedHead = removeLocalCssLinks(headContent, basename).trimEnd();
  const styleBlock = `\n    <style>\n${shareCss}\n${pageCss}\n    </style>`;
  const newHead = `${cleanedHead}${styleBlock}\n`;

  return html.replace(/<head[^>]*>[\s\S]*?<\/head>/i, `<head>\n${newHead}</head>`);
}

async function main() {
  const rawBasename = process.argv[2] || (await ask('請輸入要 merge 的 html 檔名（例如 donate）：'));
  const basename = normalizeBasename(rawBasename);

  if (!basename) {
    console.error('❌ 檔名無效，請輸入不含路徑的檔名，例如 donate');
    process.exit(1);
  }

  const rawTarget = process.argv[3] || (await ask('請輸入貼入目標（body 或 html）：'));
  const target = normalizeTarget(rawTarget);

  if (!target) {
    console.error('❌ 貼入目標無效，請輸入 body 或 html');
    process.exit(1);
  }

  const htmlPath = `${basename}.html`;
  const cssPath = `${basename}.css`;
  const shareCssPath = 'share.css';
  const outputPath = `merge_${basename}.html`;

  for (const file of [htmlPath, cssPath, shareCssPath]) {
    if (!fs.existsSync(file)) {
      console.error(`❌ 找不到檔案：${file}`);
      process.exit(1);
    }
  }

  const html = fs.readFileSync(htmlPath, 'utf-8');
  const pageCss = fs.readFileSync(cssPath, 'utf-8');
  const shareCss = fs.readFileSync(shareCssPath, 'utf-8');

  const output =
    target === 'body'
      ? buildBodyModeOutput({ html, basename, shareCss, pageCss })
      : buildHtmlModeOutput({ html, basename, shareCss, pageCss });

  fs.writeFileSync(outputPath, output, 'utf-8');
  console.log(`✅ 合併完成（${target} 模式），輸出為 ${outputPath}`);
}

main().catch((err) => {
  console.error('❌ 執行失敗：', err.message);
  process.exit(1);
});
