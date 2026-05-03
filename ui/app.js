let DB = null;
let currentMap = null;
let currentTierFilter = "all";  // all / S+ / S / A / B / C
let synergyPick1 = "";  // シナジー検索: 1人目
let synergyPick2 = "";  // シナジー検索: 2人目

const TIER_COLORS = {
  "S+": "bg-red-600 text-white",
  "S":  "bg-orange-500 text-white",
  "A":  "bg-yellow-500 text-gray-900",
  "B":  "bg-blue-500 text-white",
  "C":  "bg-gray-600 text-white",
  "?":  "bg-gray-500 text-gray-200 italic",
};
const TIER_ORDER = ["S+", "S", "A", "B", "C", "?"];
const TIER_LABELS = {
  "?": "サンプル不足 (50戦未満)",
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
  currentMap = m;
  renderMapDetail();
}

function setTierFilter(tier) {
  currentTierFilter = tier;
  renderMapDetail();
}

function setSynergyPick(slot, brawler) {
  if (slot === 1) synergyPick1 = brawler;
  else if (slot === 2) synergyPick2 = brawler;
  renderMapDetail();
}

function resetSynergy() {
  synergyPick1 = "";
  synergyPick2 = "";
  renderMapDetail();
}

function renderMapDetail() {
  const m = currentMap;
  if (!m) return;
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

  // ティア人数カウント
  const counts = {};
  for (const t of m.tier_list) counts[t.tier] = (counts[t.tier] || 0) + 1;

  // フィルタボタン
  const filterButtons = `
    <div class="flex flex-wrap gap-1 mt-3">
      <button onclick="setTierFilter('all')" class="px-3 py-1 rounded text-sm font-bold ${currentTierFilter === 'all' ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}">All ${m.tier_list.length}</button>
      ${TIER_ORDER.map(tier => {
        const count = counts[tier] || 0;
        if (count === 0) return "";
        const isActive = currentTierFilter === tier;
        const colorClass = isActive ? TIER_COLORS[tier] : "bg-gray-700 text-gray-300 hover:bg-gray-600";
        return `<button onclick="setTierFilter('${tier}')" class="px-3 py-1 rounded text-sm font-bold ${colorClass}">${tier} ${count}</button>`;
      }).join("")}
    </div>`;

  // フィルタ適用
  const filtered = currentTierFilter === "all"
    ? m.tier_list
    : m.tier_list.filter(t => t.tier === currentTierFilter);

  // 行レンダリング
  let lastTier = null;
  const rowsHtml = filtered.map(t => {
    let header = "";
    // All のときだけセクションヘッダー
    if (currentTierFilter === "all" && t.tier !== lastTier) {
      const label = TIER_LABELS[t.tier] || `Tier ${t.tier}`;
      header = `<tr class="bg-gray-700/70">
        <td colspan="7" class="py-2 px-2 font-bold">
          <span class="px-2 py-0.5 rounded text-xs font-bold ${TIER_COLORS[t.tier] || "bg-gray-500"}">${t.tier}</span>
          <span class="ml-2 text-gray-200 text-sm">${counts[t.tier]}体</span>
          ${TIER_LABELS[t.tier] ? `<span class="ml-2 text-gray-400 text-xs">${TIER_LABELS[t.tier]}</span>` : ""}
        </td>
      </tr>`;
      lastTier = t.tier;
    }
    return header + `<tr class="border-b border-gray-700/50 hover:bg-gray-700/30">
      <td class="py-2 px-2 w-12"><span class="px-2 py-0.5 rounded text-xs font-bold ${TIER_COLORS[t.tier] || "bg-gray-500"}">${t.tier}</span></td>
      <td class="py-2 px-2">
        <div class="flex items-center">
          ${t.image_url ? `<img src="${t.image_url}" class="w-8 h-8 mr-2 rounded flex-shrink-0">` : ""}
          <span class="truncate">${escapeHtml(t.brawler)}</span>
        </div>
      </td>
      <td class="py-2 px-2 text-right w-12">${t.picks}</td>
      <td class="py-2 px-2 text-right font-mono text-green-300 w-14">${((t.rank1_rate || 0) * 100).toFixed(1)}%</td>
      <td class="py-2 px-2 text-right font-mono text-blue-300 w-14">${((t.rank2_rate || 0) * 100).toFixed(1)}%</td>
      <td class="py-2 px-2 text-right font-mono w-12 hidden sm:table-cell">${(t.win_rate * 100).toFixed(1)}%</td>
      <td class="py-2 px-2 text-right font-mono w-14 hidden md:table-cell">${t.avg_rank.toFixed(2)}</td>
    </tr>`;
  }).join("");

  const tableHtml = `
    <div class="overflow-x-auto -mx-2 sm:mx-0">
    <table class="w-full">
      <thead>
        <tr class="text-left text-xs text-gray-400 border-b border-gray-700">
          <th class="pb-2 w-12 px-2">Tier</th>
          <th class="pb-2 px-2">ブロウラー</th>
          <th class="pb-2 text-right w-12 px-2">picks</th>
          <th class="pb-2 text-right w-14 px-2">1位率</th>
          <th class="pb-2 text-right w-14 px-2">2位率</th>
          <th class="pb-2 text-right w-12 px-2 hidden sm:table-cell">TOP2</th>
          <th class="pb-2 text-right w-14 px-2 hidden md:table-cell">平均順位</th>
        </tr>
      </thead>
      <tbody>${rowsHtml}</tbody>
    </table>
    </div>`;

  el.innerHTML = `
    <div class="bg-gray-800 rounded overflow-hidden">
      ${m.image_url ? `<img src="${m.image_url}" class="w-full" style="max-height:280px;object-fit:cover">` : ""}
      <div class="p-6">
        <h2 class="text-2xl font-bold">${escapeHtml(m.name_jp || m.name)}</h2>
        ${m.name_jp ? `<div class="text-sm text-gray-400">${escapeHtml(m.name)}</div>` : ""}
        <div class="text-sm text-gray-400 mt-2">
          総ピック ${m.total_picks} / 掲載 ${m.tier_list.length}人 /
          <span class="text-gray-300">マップ平均 WR ${(m.map_avg_wr * 100).toFixed(1)}%, 平均順位 ${m.map_avg_rank.toFixed(2)}</span>
          ${!m.in_pool ? '<span class="ml-2 text-yellow-500">[プール外マップ]</span>' : ""}
        </div>
        <div class="text-xs text-gray-500 mt-1">スコア: 1位+9 / 2位+4 / 3位-4 / 4位-9。高トロ帯(2000+)バトル2倍重み。ピック率5%以上は1.1倍ボーナス。300戦以下は0.9倍ペナルティ。ベイズ平均化。50戦以上の信頼サンプルでpercentileティア (50戦未満は「?」)</div>
        ${filterButtons}
        <h3 class="text-sm font-bold mt-4 mb-2 text-gray-300 uppercase tracking-wide">ティアリスト ${currentTierFilter !== 'all' ? `(${currentTierFilter}のみ)` : ''}</h3>
        ${tableHtml}

        ${renderSynergySection(m)}

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

function renderSynergySection(m) {
  if (!m.all_trios || m.all_trios.length === 0) return "";

  // 出現する全ブロウラー (sorted)
  const brawlerSet = new Set();
  for (const t of m.all_trios) {
    for (const mem of t.members) brawlerSet.add(mem.brawler);
  }
  const brawlers = [...brawlerSet].sort();

  const opt = (val, sel) =>
    `<option value="${escapeHtml(val)}" ${val === sel ? "selected" : ""}>${escapeHtml(val)}</option>`;
  const dropdown = (slot, selected) => `
    <select onchange="setSynergyPick(${slot}, this.value)" class="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm">
      <option value="">-- ${slot}人目 --</option>
      ${brawlers.map(b => opt(b, selected)).join("")}
    </select>`;

  // フィルタ: 選択されたブロウラーを含むtrios
  let filtered = m.all_trios;
  if (synergyPick1) {
    filtered = filtered.filter(t => t.members.some(mem => mem.brawler === synergyPick1));
  }
  if (synergyPick2) {
    filtered = filtered.filter(t => t.members.some(mem => mem.brawler === synergyPick2));
  }
  if (synergyPick1 && synergyPick2 && synergyPick1 === synergyPick2) {
    filtered = [];  // 同じキャラ2人選択は無効
  }

  // 表示制限
  const top = filtered.slice(0, 30);
  const selectedSet = new Set([synergyPick1, synergyPick2].filter(Boolean));

  const resultHtml = top.length === 0
    ? `<div class="p-3 text-gray-500 text-sm">該当する組み合わせなし (5戦以上のトリオから検索)</div>`
    : top.map(t => {
        const others = t.members.filter(mem => !selectedSet.has(mem.brawler));
        const wrColor = t.win_rate >= 0.75 ? "text-green-400" : t.win_rate >= 0.5 ? "text-yellow-400" : "text-red-400";
        return `<div class="flex items-center justify-between p-2 bg-gray-700/30 hover:bg-gray-700/50 rounded">
          <div class="flex items-center gap-2 flex-wrap">
            ${t.members.map((mem, i) => `
              ${i > 0 ? '<span class="text-gray-500">+</span>' : ""}
              <div class="flex items-center gap-1 px-2 py-1 ${selectedSet.has(mem.brawler) ? 'bg-blue-700/50 ring-1 ring-blue-500' : 'bg-gray-700'} rounded">
                ${mem.image_url ? `<img src="${mem.image_url}" class="w-6 h-6 rounded">` : ""}
                <span class="text-xs sm:text-sm">${escapeHtml(mem.brawler)}</span>
              </div>
            `).join("")}
          </div>
          <div class="text-sm whitespace-nowrap ml-2">
            <span class="font-mono font-bold ${wrColor}">${(t.win_rate * 100).toFixed(0)}%</span>
            <span class="text-gray-400 ml-1 font-mono text-xs">${t.wins}/${t.picks}</span>
          </div>
        </div>`;
      }).join("");

  const hint = !synergyPick1
    ? "1人目を選ぶと相方候補、2人決めると3人目候補が出ます"
    : !synergyPick2
      ? `${synergyPick1} の相方候補TOP30 (勝率順)`
      : `${synergyPick1} + ${synergyPick2} の3人目候補TOP30 (勝率順)`;

  return `
    <h3 class="text-sm font-bold mt-6 mb-2 text-gray-300 uppercase tracking-wide">シナジー検索 / ピック提案</h3>
    <div class="bg-gray-700/20 p-3 rounded mb-2">
      <div class="flex flex-wrap gap-2 items-center mb-2">
        ${dropdown(1, synergyPick1)}
        ${dropdown(2, synergyPick2)}
        ${(synergyPick1 || synergyPick2) ? `<button onclick="resetSynergy()" class="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm">クリア</button>` : ""}
      </div>
      <div class="text-xs text-gray-400 mb-2">${hint}</div>
      <div class="space-y-1 max-h-96 overflow-y-auto">${resultHtml}</div>
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
