let DB = null;

const TIER_COLORS = {
  "S+": "bg-red-600 text-white",
  "S":  "bg-orange-500 text-white",
  "A":  "bg-yellow-500 text-gray-900",
  "B":  "bg-blue-500 text-white",
  "C":  "bg-gray-600 text-white",
};

async function load() {
  try {
    const res = await fetch("/data/db.json");
    DB = await res.json();
  } catch (e) {
    document.getElementById("meta-info").textContent =
      "db.json の読込失敗。HTTPサーバ経由で開いてください: py -m http.server 8000";
    return;
  }
  const ts = new Date(DB.generated_at);
  document.getElementById("meta-info").textContent =
    `最終更新: ${ts.toLocaleString("ja-JP")} / 集計 ${DB.stats.total_picks.toLocaleString()}戦 / マップ ${DB.stats.total_maps} / ブロウラー ${DB.stats.total_brawlers}`;
  renderMapList();
  if (DB.maps.length) selectMap(DB.maps[0]);
  renderBrawlerGrid();
  setupTabs();
  setupSearch();
}

function renderMapList() {
  const el = document.getElementById("map-list");
  el.innerHTML = DB.maps.map(m => `
    <div class="map-item p-3 bg-gray-800 hover:bg-gray-700 cursor-pointer rounded border border-transparent hover:border-blue-500 ${!m.in_pool ? "opacity-60" : ""}" data-hash="${m.hash}">
      <div class="flex justify-between items-center">
        <span class="font-semibold">${escapeHtml(m.name_jp || m.name)}</span>
        <span class="text-xs text-gray-400 ml-2">${m.total_picks}</span>
      </div>
      ${m.name_jp ? `<div class="text-xs text-gray-500">${escapeHtml(m.name)}</div>` : ""}
      ${!m.in_pool ? `<div class="text-xs text-yellow-500 mt-1">プール外</div>` : ""}
    </div>
  `).join("");
  el.querySelectorAll(".map-item").forEach(node => {
    node.addEventListener("click", () => {
      const m = DB.maps.find(x => x.hash === node.dataset.hash);
      selectMap(m);
      el.querySelectorAll(".map-item").forEach(n => n.classList.remove("border-blue-500"));
      node.classList.add("border-blue-500");
    });
  });
}

function selectMap(m) {
  const el = document.getElementById("map-detail");
  if (!m.tier_list || m.tier_list.length === 0) {
    el.innerHTML = `
      <div class="bg-gray-800 p-6 rounded">
        <h2 class="text-xl font-bold">${escapeHtml(m.name_jp || m.name)}</h2>
        <div class="text-sm text-gray-400 mt-1">${escapeHtml(m.name)}</div>
        <div class="mt-4 p-4 bg-yellow-900/30 border border-yellow-700 rounded text-yellow-200">
          このマップのデータが不足しています (総ピック ${m.total_picks})。<br>
          ローテーションで戻ってきたら再クロールしてください。
        </div>
      </div>`;
    return;
  }
  el.innerHTML = `
    <div class="bg-gray-800 rounded overflow-hidden">
      ${m.image_url ? `<img src="${m.image_url}" class="w-full" style="max-height:280px;object-fit:cover">` : ""}
      <div class="p-6">
        <h2 class="text-2xl font-bold">${escapeHtml(m.name_jp || m.name)}</h2>
        ${m.name_jp ? `<div class="text-sm text-gray-400">${escapeHtml(m.name)}</div>` : ""}
        <div class="text-sm text-gray-400 mt-2">
          総ピック ${m.total_picks} / 掲載 ${m.tier_list.length}人
          ${!m.in_pool ? '<span class="ml-2 text-yellow-500">[プール外マップ]</span>' : ""}
        </div>
        <h3 class="text-sm font-bold mt-4 mb-2 text-gray-300 uppercase tracking-wide">ティアリスト</h3>
        <table class="w-full">
          <thead>
            <tr class="text-left text-xs text-gray-400 border-b border-gray-700">
              <th class="pb-2 w-14">Tier</th>
              <th class="pb-2">ブロウラー</th>
              <th class="pb-2 text-right w-16">picks</th>
              <th class="pb-2 text-right w-16">WR</th>
              <th class="pb-2 text-right w-16">avgRk</th>
            </tr>
          </thead>
          <tbody>
            ${m.tier_list.map(t => `
              <tr class="border-b border-gray-700/50 hover:bg-gray-700/30">
                <td class="py-2"><span class="px-2 py-0.5 rounded text-xs font-bold ${TIER_COLORS[t.tier] || "bg-gray-500"}">${t.tier}</span></td>
                <td class="py-2">
                  <div class="flex items-center">
                    ${t.image_url ? `<img src="${t.image_url}" class="w-8 h-8 mr-2 rounded">` : ""}
                    <span>${escapeHtml(t.brawler)}</span>
                  </div>
                </td>
                <td class="py-2 text-right">${t.picks}</td>
                <td class="py-2 text-right font-mono">${(t.win_rate * 100).toFixed(1)}%</td>
                <td class="py-2 text-right font-mono">${t.avg_rank.toFixed(2)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>

        ${m.recommended_trios && m.recommended_trios.length > 0 ? `
          <h3 class="text-sm font-bold mt-6 mb-2 text-gray-300 uppercase tracking-wide">推奨トリオ編成</h3>
          <div class="space-y-2">
            ${m.recommended_trios.map(t => `
              <div class="flex items-center justify-between p-3 bg-gray-700/30 hover:bg-gray-700/50 rounded">
                <div class="flex items-center gap-2 flex-wrap">
                  ${t.members.map((mem, i) => `
                    ${i > 0 ? '<span class="text-gray-500">+</span>' : ''}
                    <div class="flex items-center gap-1 px-2 py-1 bg-gray-700 rounded">
                      ${mem.image_url ? `<img src="${mem.image_url}" class="w-6 h-6 rounded">` : ''}
                      <span class="text-sm">${escapeHtml(mem.brawler)}</span>
                    </div>
                  `).join("")}
                </div>
                <div class="text-sm whitespace-nowrap ml-2">
                  <span class="font-mono font-bold ${t.win_rate >= 0.75 ? 'text-green-400' : t.win_rate >= 0.5 ? 'text-yellow-400' : 'text-red-400'}">${(t.win_rate * 100).toFixed(0)}%</span>
                  <span class="text-gray-400 ml-2 font-mono">${t.wins}/${t.picks}</span>
                </div>
              </div>
            `).join("")}
          </div>
        ` : ""}
      </div>
    </div>`;
}

function renderBrawlerGrid(filter = "") {
  const el = document.getElementById("brawler-grid");
  const f = filter.toLowerCase();
  const list = DB.brawlers.filter(b => !f || b.name.toLowerCase().includes(f));
  el.innerHTML = list.map(b => `
    <div class="brawler-card p-2 bg-gray-800 hover:bg-gray-700 cursor-pointer rounded text-center border border-transparent hover:border-blue-500" data-name="${escapeHtml(b.name)}">
      ${b.image_url ? `<img src="${b.image_url}" class="w-full rounded">` : '<div class="w-full aspect-square bg-gray-700 rounded"></div>'}
      <div class="text-xs mt-1 truncate font-semibold">${escapeHtml(b.name)}</div>
      <div class="text-xs text-gray-500">${b.total_picks}p</div>
    </div>
  `).join("");
  el.querySelectorAll(".brawler-card").forEach(node => {
    node.addEventListener("click", () => {
      const b = DB.brawlers.find(x => x.name === node.dataset.name);
      selectBrawler(b);
      el.querySelectorAll(".brawler-card").forEach(n => n.classList.remove("border-blue-500"));
      node.classList.add("border-blue-500");
    });
  });
}

function selectBrawler(b) {
  const el = document.getElementById("brawler-detail");
  el.innerHTML = `
    <div class="bg-gray-800 p-6 rounded">
      <div class="flex items-center mb-6">
        ${b.image_url ? `<img src="${b.image_url}" class="w-20 h-20 rounded mr-4">` : ""}
        <div>
          <h2 class="text-2xl font-bold">${escapeHtml(b.name)}</h2>
          <div class="text-sm text-gray-400">${escapeHtml(b.rarity || "")} / 総ピック ${b.total_picks}</div>
        </div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h3 class="font-bold mb-3 text-green-400">強いマップ</h3>
          ${(b.best_maps || []).length === 0
            ? '<div class="text-gray-500 text-sm">サンプル不足</div>'
            : b.best_maps.map(m => `
              <div class="flex justify-between items-center p-2 hover:bg-gray-700/50 rounded">
                <span>${escapeHtml(m.map)}</span>
                <span class="text-sm font-mono">${(m.win_rate * 100).toFixed(1)}% (${m.picks}p)</span>
              </div>
            `).join("")}
        </div>
        <div>
          <h3 class="font-bold mb-3 text-red-400">弱いマップ</h3>
          ${(b.worst_maps || []).length === 0
            ? '<div class="text-gray-500 text-sm">サンプル不足</div>'
            : b.worst_maps.map(m => `
              <div class="flex justify-between items-center p-2 hover:bg-gray-700/50 rounded">
                <span>${escapeHtml(m.map)}</span>
                <span class="text-sm font-mono">${(m.win_rate * 100).toFixed(1)}% (${m.picks}p)</span>
              </div>
            `).join("")}
        </div>
      </div>
    </div>`;
}

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => {
        b.classList.remove("bg-blue-600");
        b.classList.add("bg-gray-700");
      });
      btn.classList.remove("bg-gray-700");
      btn.classList.add("bg-blue-600");
      document.querySelectorAll(".tab-content").forEach(c => c.classList.add("hidden"));
      document.getElementById("tab-" + btn.dataset.tab).classList.remove("hidden");
    });
  });
}

function setupSearch() {
  document.getElementById("brawler-search").addEventListener("input", e => {
    renderBrawlerGrid(e.target.value);
  });
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

load();
