/**
 * 新官網文章樣式確認
 * 與 colleague-confirm.html 一起貼到 Apps Script。
 * 第一次有人開啟或送出時，會在部署者的 Google 雲端硬碟建立試算表「新官網文章樣式確認」。
 * 姓名綁定 Google 帳號；讀不到帳號時，改綁這台瀏覽器送出的憑證。
 */
var HEADERS_ = ['姓名', '信箱', '憑證', '題目', '種類', '選擇', '意見', '更新時間'];
var CHOICES_ = {
  list: { kind: 'style', values: { agree: true, disagree: true } },
  heading: { kind: 'style', values: { agree: true, disagree: true } },
  image: { kind: 'style', values: { agree: true, disagree: true } },
  table: { kind: 'style', values: { agree: true, disagree: true } },
  quote: { kind: 'style', values: { agree: true, disagree: true } },
  joint: { kind: 'style', values: { agree: true, disagree: true } },
  'event-title': { kind: 'style', values: { agree: true, disagree: true } },
  recap: { kind: 'style', values: { agree: true, disagree: true } },
  'q-info': { kind: 'vote', values: { 'h2-ul': true, 'strong-ul': true } },
  'q-speaker': { kind: 'vote', values: { slash: true, pipe: true, paren: true } },
  'q-hr': { kind: 'vote', values: { 'no-hr': true, hr: true } },
  'q-quote-label': { kind: 'vote', values: { 'with-label': true, 'no-label': true } },
  'q-more': { kind: 'vote', values: { h2: true, bracket: true } }
};

function doGet() {
  return HtmlService.createHtmlOutputFromFile('colleague-confirm')
    .setTitle('新官網文章樣式確認')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function loadAll(token) {
  return withLock_(function () {
    var sh = ensureSheet_();
    return exportState_(readRows_(sh), token);
  });
}

function saveBatch(payload) {
  if (!payload || !payload.items || !payload.items.length) throw new Error('沒有可送出的填答');
  if (payload.items.length > 30) throw new Error('題目數量不正確');
  var name = cleanName_(payload.name);
  var incoming = normalizeItems_(payload.items);
  if (!incoming.length) throw new Error('沒有可送出的填答');
  return withLock_(function () {
    var sh = ensureSheet_();
    var rows = readRows_(sh);
    var actor = actorFrom_(payload.token, true);
    var ownerId = ownerIdForName_(rows, name);
    if (ownerId && ownerId !== actor.id) throw new Error('這個姓名已經有人使用');
    var previousName = nameForActor_(rows, actor.id);
    if (previousName && previousName !== name) {
      rows.forEach(function (row) {
        if (rowActorId_(row) === actor.id) row.name = name;
      });
    }
    rows.forEach(function (row) {
      if (row.name === name && !rowActorId_(row)) {
        row.email = actor.email;
        row.token = actor.token;
      }
    });
    var nowMs = Date.now();
    var renaming = !!(previousName && previousName !== name);
    var conflicts = [];
    incoming.forEach(function (item) {
      var existing = latestRow_(rows, name, item.item);
      if (!existing) {
        if (!item.clear && item.baseUpdatedAt > 0) conflicts.push(item.item);
        return;
      }
      if (existing.updatedAt <= item.baseUpdatedAt) return;
      if (renaming && rowActorId_(existing) === actor.id && !item.clear) return;
      if (item.clear || existing.choice !== item.choice || existing.comment !== item.comment) {
        conflicts.push(item.item);
      }
    });
    if (conflicts.length) {
      var stale = exportState_(readRows_(sh), payload.token);
      stale.ok = false;
      stale.conflicts = conflicts;
      return stale;
    }
    incoming.forEach(function (item) {
      var existing = latestRow_(rows, name, item.item);
      rows = rows.filter(function (row) {
        return !(row.name === name && row.item === item.item);
      });
      if (item.clear) return;
      if (existing && existing.choice === item.choice && existing.comment === item.comment) {
        existing.name = name;
        existing.email = actor.email;
        existing.token = actor.token;
        rows.push(existing);
        return;
      }
      rows.push({
        name: name,
        email: actor.email,
        token: actor.token,
        item: item.item,
        kind: CHOICES_[item.item].kind,
        choice: item.choice,
        comment: item.comment,
        updatedAt: nowMs
      });
    });
    rows = collapseRows_(rows);
    writeRows_(sh, rows);
    SpreadsheetApp.flush();
    var saved = exportState_(rows, payload.token);
    saved.ok = true;
    return saved;
  });
}

function withLock_(fn) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    return fn();
  } finally {
    lock.releaseLock();
  }
}

function openOrCreate_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('SHEET_ID');
  if (id) return SpreadsheetApp.openById(id);
  var created = SpreadsheetApp.create('新官網文章樣式確認');
  var winner = props.getProperty('SHEET_ID');
  if (winner) return SpreadsheetApp.openById(winner);
  props.setProperty('SHEET_ID', created.getId());
  return created;
}

function ensureSheet_() {
  var ss = openOrCreate_();
  var sh = ss.getSheetByName('填答');
  if (!sh) {
    sh = ss.getSheets()[0];
    sh.setName('填答');
  }
  if (sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, HEADERS_.length).setValues([HEADERS_]);
    return sh;
  }
  var width = Math.max(sh.getLastColumn(), 1);
  var headerRow = sh.getRange(1, 1, 1, width).getValues()[0].map(function (cell) {
    return String(cell || '').trim();
  });
  while (headerRow.length && !headerRow[headerRow.length - 1]) headerRow.pop();
  if (sameHeaders_(headerRow, HEADERS_)) return sh;
  var allowed = {};
  HEADERS_.forEach(function (header) { allowed[header] = true; });
  var unexpected = headerRow.filter(function (header) { return header && !allowed[header]; });
  var missingCore = ['姓名', '題目', '種類', '選擇', '意見', '更新時間'].some(function (header) {
    return headerRow.indexOf(header) === -1;
  });
  if (unexpected.length || missingCore) throw new Error('試算表欄位與程式不符，請聯絡部署者');
  writeRows_(sh, readRows_(sh));
  return sh;
}

function sameHeaders_(actual, expected) {
  if (actual.length !== expected.length) return false;
  for (var i = 0; i < expected.length; i++) {
    if (actual[i] !== expected[i]) return false;
  }
  return true;
}

function readRows_(sh) {
  var values = sh.getDataRange().getValues();
  if (!values.length) return [];
  var headers = values[0].map(function (cell) { return String(cell || '').trim(); });
  var index = {};
  headers.forEach(function (header, i) {
    if (header && !Object.prototype.hasOwnProperty.call(index, header)) index[header] = i;
  });
  var rows = [];
  for (var r = 1; r < values.length; r++) {
    var name = String(valueAt_(values[r], index, '姓名') || '').trim();
    var item = String(valueAt_(values[r], index, '題目') || '').trim();
    if (!name || !item || !isSafeName_(name)) continue;
    rows.push({
      name: name,
      email: String(valueAt_(values[r], index, '信箱') || '').trim().toLowerCase(),
      token: String(valueAt_(values[r], index, '憑證') || '').trim(),
      item: item,
      kind: String(valueAt_(values[r], index, '種類') || '').trim(),
      choice: String(valueAt_(values[r], index, '選擇') || '').trim(),
      comment: String(valueAt_(values[r], index, '意見') || '').trim(),
      updatedAt: timeOf_(valueAt_(values[r], index, '更新時間'))
    });
  }
  return collapseRows_(rows);
}

function valueAt_(row, index, header) {
  if (!Object.prototype.hasOwnProperty.call(index, header)) return '';
  return row[index[header]];
}

function writeRows_(sh, rows) {
  var table = [HEADERS_];
  rows.forEach(function (row) {
    table.push([
      asText_(row.name),
      asText_(row.email),
      asText_(row.token),
      asText_(row.item),
      asText_(row.kind),
      asText_(row.choice),
      asText_(row.comment),
      row.updatedAt ? new Date(row.updatedAt) : ''
    ]);
  });
  var oldRows = Math.max(sh.getLastRow(), table.length);
  var oldCols = Math.max(sh.getLastColumn(), HEADERS_.length);
  sh.getRange(1, 1, table.length, HEADERS_.length).setValues(table);
  if (oldRows > table.length) {
    sh.getRange(table.length + 1, 1, oldRows - table.length, oldCols).clearContent();
  }
  if (oldCols > HEADERS_.length) {
    sh.getRange(1, HEADERS_.length + 1, table.length, oldCols - HEADERS_.length).clearContent();
  }
}

function collapseRows_(rows) {
  var map = {};
  rows.forEach(function (row) {
    var key = row.name + '\n' + row.item;
    var prev = map[key];
    if (!prev || row.updatedAt >= prev.updatedAt) map[key] = row;
  });
  var list = [];
  Object.keys(map).forEach(function (key) { list.push(map[key]); });
  return list;
}

function latestRow_(rows, name, item) {
  var found = null;
  rows.forEach(function (row) {
    if (row.name === name && row.item === item) found = row;
  });
  return found;
}

function rowActorId_(row) {
  if (row.email) return 'email:' + row.email;
  if (row.token) return 'token:' + row.token;
  return '';
}

function ownerIdForName_(rows, name) {
  var owner = '';
  var time = -1;
  rows.forEach(function (row) {
    if (row.name !== name) return;
    var id = rowActorId_(row);
    if (!id || row.updatedAt < time) return;
    time = row.updatedAt;
    owner = id;
  });
  return owner;
}

function nameForActor_(rows, actorId) {
  var name = '';
  var time = -1;
  rows.forEach(function (row) {
    if (rowActorId_(row) !== actorId || row.updatedAt < time) return;
    time = row.updatedAt;
    name = row.name;
  });
  return name;
}

function exportState_(rows, token) {
  var actor = actorFrom_(token, false);
  var people = {};
  var owners = {};
  var selfName = '';
  var selfTime = -1;
  rows.forEach(function (row) {
    if (!isSafeName_(row.name)) return;
    var spec = CHOICES_[row.item];
    var ownerId = ownerIdForName_(rows, row.name);
    if (!Object.prototype.hasOwnProperty.call(owners, row.name)) {
      owners[row.name] = !ownerId ? 'open' : (ownerId === actor.id ? 'self' : 'other');
    }
    if (actor.id && rowActorId_(row) === actor.id && row.updatedAt >= selfTime) {
      selfTime = row.updatedAt;
      selfName = row.name;
    }
    if (!spec) return;
    if (!Object.prototype.hasOwnProperty.call(people, row.name)) {
      people[row.name] = { styles: {}, votes: {} };
    }
    var bucket = spec.kind === 'vote' ? 'votes' : 'styles';
    var prev = people[row.name][bucket][row.item];
    if (prev && prev.updatedAt > row.updatedAt) return;
    people[row.name][bucket][row.item] = {
      choice: row.choice,
      comment: row.comment,
      updatedAt: row.updatedAt
    };
  });
  return { people: people, selfName: selfName, owners: owners };
}

function normalizeItems_(items) {
  var seen = {};
  items.forEach(function (item) {
    if (!item) throw new Error('題目或選項不正確');
    var id = String(item.item || '');
    var spec = CHOICES_[id];
    if (!spec) throw new Error('題目或選項不正確');
    var clear = item.clear === true;
    var choice = clear ? '' : String(item.choice || '');
    if (!clear && !Object.prototype.hasOwnProperty.call(spec.values, choice)) {
      throw new Error('題目或選項不正確');
    }
    var base = Number(item.baseUpdatedAt);
    if (!isFinite(base) || base < 0) base = 0;
    seen[id] = {
      item: id,
      clear: clear,
      choice: choice,
      comment: clear ? '' : cleanComment_(item.comment),
      baseUpdatedAt: base
    };
  });
  var list = [];
  Object.keys(seen).forEach(function (id) { list.push(seen[id]); });
  return list;
}

function actorFrom_(token, strict) {
  var email = '';
  try {
    email = String(Session.getActiveUser().getEmail() || '').trim().toLowerCase();
  } catch (err) {
    email = '';
  }
  if (email) return { id: 'email:' + email, email: email, token: '' };
  var text = String(token || '');
  if (!/^[A-Za-z0-9._~-]{16,80}$/.test(text)) {
    if (strict) throw new Error('缺少這台電腦的憑證');
    return { id: '', email: '', token: '' };
  }
  var hash = hashToken_(text);
  return { id: 'token:' + hash, email: '', token: hash };
}

function hashToken_(token) {
  var bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, token, Utilities.Charset.UTF_8);
  return Utilities.base64EncodeWebSafe(bytes);
}

function cleanName_(value) {
  var text = String(value == null ? '' : value).replace(/[\u0000-\u001F\u007F]/g, '').trim();
  if (!text) throw new Error('缺少姓名');
  if (!isSafeName_(text)) throw new Error('這個姓名無法使用');
  if (text.length > 30) throw new Error('姓名請在 30 字以內');
  return text;
}

function cleanComment_(value) {
  var text = String(value == null ? '' : value).replace(/\u0000/g, '').trim();
  if (text.length > 1000) throw new Error('意見請在 1000 字以內');
  return text;
}

function isSafeName_(name) {
  return !!name && name !== '__proto__' && name !== 'constructor' && name !== 'prototype';
}

function asText_(value) {
  var text = String(value == null ? '' : value);
  if (/^[=+\-@\t\r]/.test(text)) return "'" + text;
  return text;
}

function timeOf_(value) {
  if (Object.prototype.toString.call(value) === '[object Date]' && !isNaN(value.getTime())) return value.getTime();
  if (typeof value === 'number' && isFinite(value)) return value;
  return 0;
}
