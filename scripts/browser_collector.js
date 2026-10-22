// Fallback khi máy chạy Python không gọi được dichvucong.gov.vn (bị chặn mạng/WAF).
// Cách dùng: mở https://dichvucong.gov.vn/co-quan trong trình duyệt, F12 -> Console,
// sửa PROVINCE bên dưới, dán toàn bộ file này và Enter. Khi xong, bấm nút đỏ
// "TẢI DỮ LIỆU" ở góc trái trên để tải file <PROVINCE>_raw.json.gz
// rồi chạy:  python build_callbot_excel.py --raw <file> --province <PROVINCE> --out <xlsx>
(async () => {
  const PROVINCE = 'H19';            // H19 = Thành phố Đồng Nai, H31 = Hưng Yên ...
  const INCLUDE_INTERNAL = false;    // true để lấy cả TTHC nội bộ (STANDARD_INTERNAL)
  const WORKERS = 4;

  const api = (path, body) => fetch('/api/v1' + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  }).then(async r => { const t = await r.text(); if (t.trim().startsWith('<')) throw new Error('HTML ' + r.status); return JSON.parse(t); });
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const log = (...a) => console.log('[TTHC]', ...a);

  // 1. Danh sách
  const items = {};
  for (const [level, dept] of [['PROVINCE', ''], ['COMMUNE', ''], [null, PROVINCE]]) {
    let last = '';
    for (;;) {
      const body = { limit: 100, lastId: last, q: '', categoryId: '', departmentCode: dept };
      if (level) body.level = level;
      let j;
      try { j = await api('/submitting/formality/list-all-public-formality-by-citizen', body); }
      catch (e) { log('retry list', e.message); await sleep(2000); continue; }
      if (!j.data) { log('list error', j.message); break; }
      for (const it of j.data.items) {
        const o = items[it.id] || { ...it, _levels: [] }; o._levels.push(level || PROVINCE); items[it.id] = o;
      }
      log(`list ${level || dept}: ${Object.keys(items).length}/${j.data.total}`);
      if (!j.data.items.length || !j.data.lastId || j.data.lastId === last) break;
      last = j.data.lastId;
    }
  }
  const keep = new Set(['STANDARD', 'INTERCONNECTED'].concat(INCLUDE_INTERNAL ? ['STANDARD_INTERNAL'] : []));
  const scope = Object.fromEntries(Object.entries(items).filter(([, x]) =>
    keep.has(x.type) || (x.type === 'SPECIFIC' && x._levels.includes(PROVINCE))));
  const ids = Object.keys(scope);
  log(`Chọn ${ids.length} TTHC cho ${PROVINCE}`);

  // 2. Chi tiết
  const details = {}, failures = []; let i = 0, done = 0;
  const worker = async () => {
    while (i < ids.length) {
      const id = ids[i++];
      for (let a = 0; a < 4; a++) {
        try {
          const j = await api('/configuring/formality/get-formality-by-citizen', { id });
          if (j.code === 'OK') { details[id] = j.data; break; }
          if (a === 3) failures.push([id, j.code]);
        } catch (e) { if (a === 3) failures.push([id, e.message]); await sleep(1500 * (a + 1)); }
      }
      if (++done % 100 === 0) log(`chi tiết ${done}/${ids.length}`);
    }
  };
  await Promise.all(Array.from({ length: WORKERS }, worker));
  log(`Xong: ${Object.keys(details).length} chi tiết, ${failures.length} lỗi`);

  // 3. Đóng gói + nút tải
  const payload = JSON.stringify({ fetchedAt: new Date().toISOString(), provinceCode: PROVINCE, list: scope, details, failures });
  const gz = await new Response(new Blob([payload]).stream().pipeThrough(new CompressionStream('gzip'))).blob();
  window.__tthc = { gz, details, scope, failures };
  const b = document.createElement('button');
  b.textContent = `TẢI DỮ LIỆU ${PROVINCE} (${(gz.size / 1e6).toFixed(1)} MB)`;
  b.style.cssText = 'position:fixed;top:10px;left:10px;z-index:999999;padding:16px;background:#c00;color:#fff;font-size:18px;border-radius:8px';
  b.onclick = () => { const a = document.createElement('a'); a.href = URL.createObjectURL(gz); a.download = `${PROVINCE}_raw.json.gz`; document.body.appendChild(a); a.click(); };
  document.body.appendChild(b);
  log('Bấm nút đỏ để tải file.');
})();
