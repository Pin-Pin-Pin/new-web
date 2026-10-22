/**
 * 新官網文章樣式確認
 * 與 colleague-confirm.html 一起貼到 Apps Script。
 * 第一次有人儲存時，會在你的 Google 雲端硬碟建立試算表「新官網文章樣式確認」。
 */
function doGet() {
  return HtmlService.createHtmlOutputFromFile('colleague-confirm')
    .setTitle('新官網文章樣式確認')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function getSpreadsheet_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('SHEET_ID');
  var ss;
  if (id) {
    ss = SpreadsheetApp.openById(id);
  } else {
    ss = SpreadsheetApp.create('新官網文章樣式確認');
    props.setProperty('SHEET_ID', ss.getId());
  }
  var sh = ss.getSheetByName('填答');
  if (!sh) {
    sh = ss.getSheets()[0];
    sh.setName('填答');
  }
  if (sh.getLastRow() === 0) {
    sh.appendRow(['姓名', '題目', '種類', '選擇', '意見', '更新時間']);
  }
  return ss;
}

function loadAll() {
  var sh = getSpreadsheet_().getSheetByName('填答');
  var values = sh.getDataRange().getValues();
  var people = {};
  for (var i = 1; i < values.length; i++) {
    var name = String(values[i][0] || '').trim();
    if (!name) continue;
    if (!people[name]) people[name] = { styles: {}, votes: {} };
    var item = String(values[i][1] || '');
    var kind = String(values[i][2] || '');
    var choice = String(values[i][3] || '');
    var comment = String(values[i][4] || '');
    if (kind === 'vote') people[name].votes[item] = choice;
    else people[name].styles[item] = { choice: choice, comment: comment };
  }
  return people;
}

function saveItem(payload) {
  if (!payload || !payload.name || !payload.item) {
    throw new Error('缺少姓名或題目');
  }
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    var sh = getSpreadsheet_().getSheetByName('填答');
    var values = sh.getDataRange().getValues();
    var row = -1;
    for (var i = 1; i < values.length; i++) {
      if (String(values[i][0]) === payload.name && String(values[i][1]) === payload.item) {
        row = i + 1;
        break;
      }
    }
    var record = [
      String(payload.name).trim(),
      String(payload.item),
      String(payload.kind || 'style'),
      String(payload.choice || ''),
      String(payload.comment || ''),
      new Date()
    ];
    if (row > 0) sh.getRange(row, 1, 1, 6).setValues([record]);
    else sh.appendRow(record);
  } finally {
    lock.releaseLock();
  }
  return { ok: true };
}
