let DB = null;
let ROTATION = null;  // {cycle_days, anchor_date, rotation: [...]}
let currentMap = null;
let currentTierFilter = "all";  // all / S+ / S / A / B / C
let synergyPick1 = "";  // シナジー検索: 1人目
let synergyPick2 = "";  // シナジー検索: 2人目

// マイページAPI のホスト (Cloudflare Tunnel の HTTPS URL)
// ローカル開発時は localStorage に "api_host" を入れれば上書きできる
const API_HOST = localStorage.getItem("api_host") || "https://api.brawl-showdown.com";
const MYPAGE_BATTLES_PER_PAGE = 40;  // ヒートマップ: 横10列×4行 = 40試合/ページ
let MYPAGE_DATA = null;
let MYPAGE_COOLDOWN_TIMER = null;
let MYPAGE_BATTLES_PAGE = 1;
let MYPAGE_BATTLES_TOTAL = 0;
let MYPAGE_PERIOD = localStorage.getItem("mypage_period") || "all";  // "all" | "30d" | "7d" | "1d"

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
  // ローテーション情報 (失敗しても致命的ではない)
  try {
    const r = await fetch("/data/map_rotation.json");
    if (r.ok) ROTATION = await r.json();
  } catch (e) { /* skip */ }

  const ts = new Date(DB.generated_at);
  document.getElementById("meta-info").textContent =
    `最終更新: ${ts.toLocaleString("ja-JP")} / 集計 ${DB.stats.total_picks.toLocaleString()}戦 / マップ ${DB.stats.total_maps} / ブロウラー ${DB.stats.total_brawlers}`;
  renderRotationBanner();
  renderMapList();
  if (DB.maps.length) selectMap(DB.maps[0]);
  renderBrawlerGrid();
  setupTabs();
  setupSearch();
}

// ローテーション計算: 指定日付 (Date) のマップ名(JP)を返す
function rotationMapForDate(date) {
  if (!ROTATION) return null;
  const anchor = new Date(ROTATION.anchor_date + "T00:00:00");
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.floor((target - anchor) / 86400000);
  const idx = ((diffDays % ROTATION.cycle_days) + ROTATION.cycle_days) % ROTATION.cycle_days;
  return ROTATION.rotation[idx];
}

// 指定マップ(JP名)の次回出現日を返す: {date: Date, daysAhead: number} or null
function nextAppearance(mapJp) {
  if (!ROTATION) return null;
  const today = new Date();
  for (let d = 0; d < ROTATION.cycle_days; d++) {
    const t = new Date(today.getFullYear(), today.getMonth(), today.getDate() + d);
    if (rotationMapForDate(t) === mapJp) return { date: t, daysAhead: d };
  }
  return null;
}

function renderRotationBanner() {
  const el = document.getElementById("rotation-banner");
  if (!el || !ROTATION) return;
  const today = new Date();
  const items = [];
  for (let d = 0; d < 3; d++) {
    const t = new Date(today.getFullYear(), today.getMonth(), today.getDate() + d);
    const map = rotationMapForDate(t);
    const label = d === 0 ? "今日" : d === 1 ? "明日" : `${t.getMonth() + 1}/${t.getDate()}`;
    const color = d === 0 ? "text-yellow-300 font-bold" : "text-gray-200";
    items.push(`<span class="${color}">${label}</span>: <span class="text-white font-semibold">${escapeHtml(map || "?")}</span>`);
  }
  el.innerHTML = `
    <div class="text-xs sm:text-sm text-gray-400 flex flex-wrap items-center gap-x-3 gap-y-1">
      <span class="text-gray-500">📅 ローテ</span>
      ${items.join('<span class="text-gray-600">·</span>')}
      <span class="text-gray-600 hidden sm:inline">·</span>
      <span class="text-gray-500 text-xs">2週間周期</span>
    </div>`;
}

function renderMapList() {
  const sel = document.getElementById("map-select");
  let candidates;
  if (ROTATION) {
    // 周期14マップを基準に並べる (DBに居ないマップもプレースホルダ生成)
    const dbByJp = new Map();
    for (const m of DB.maps) dbByJp.set(m.name_jp || m.name, m);
    candidates = ROTATION.rotation.map(jp => {
      const m = dbByJp.get(jp);
      if (m) return m;
      // データ未蓄積マップのプレースホルダ (hash プレフィックスで識別)
      return {
        hash: "__missing__" + jp,
        name: jp,
        name_jp: jp,
        total_picks: 0,
        in_pool: true,
        tier_list: [],
        recommended_trios: [],
        all_trios: [],
        _placeholder: true,
      };
    });
    candidates.sort((a, b) => {
      const aN = nextAppearance(a.name_jp || a.name);
      const bN = nextAppearance(b.name_jp || b.name);
      return (aN ? aN.daysAhead : 999) - (bN ? bN.daysAhead : 999);
    });
  } else {
    candidates = [...DB.maps].sort((a, b) => {
      if (a.in_pool !== b.in_pool) return a.in_pool ? -1 : 1;
      return b.total_picks - a.total_picks;
    });
  }
  // candidates をグローバルに保持しておく (selectMap 用)
  DB._mapCandidates = candidates;
  sel.innerHTML = candidates.map(m => {
    const next = nextAppearance(m.name_jp || m.name);
    let badge = "";
    if (next) {
      if (next.daysAhead === 0) badge = " 【今日】";
      else if (next.daysAhead === 1) badge = " 【明日】";
      else badge = ` 【${next.daysAhead}日後】`;
    } else if (!ROTATION && !m.in_pool) {
      badge = " ★プール外";
    }
    const dataMark = m._placeholder ? " ⏳" : "";
    const label = `${m.name_jp || m.name} (${m.total_picks})${badge}${dataMark}`;
    return `<option value="${escapeHtml(m.hash)}">${escapeHtml(label)}</option>`;
  }).join("");
  sel.addEventListener("change", () => {
    const m = (DB._mapCandidates || DB.maps).find(x => x.hash === sel.value);
    if (m) selectMap(m);
  });
}

function selectMap(m) {
  currentMap = m;
  // dropdown と同期
  const sel = document.getElementById("map-select");
  if (sel && sel.value !== m.hash) sel.value = m.hash;
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
          <span class="truncate">${escapeHtml(t.brawler_jp || t.brawler)}</span>
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
        <div class="text-xs text-gray-500 mt-1">スコア: 1位+9 / 2位+4 / 3位-4 / 4位-9。高トロ帯(2000+)バトル2倍。500戦以下は0.9倍ペナルティ。ベイズ平均化。50戦以上でpercentileティア</div>
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
                      <span class="text-sm">${escapeHtml(mem.brawler_jp || mem.brawler)}</span>
                    </div>
                  `).join("")}
                </div>
                <div class="text-sm whitespace-nowrap ml-2 flex items-center gap-2">
                  <span class="font-mono font-bold ${t.win_rate >= 0.75 ? 'text-green-400' : t.win_rate >= 0.5 ? 'text-yellow-400' : 'text-red-400'}">${(t.win_rate * 100).toFixed(0)}%</span>
                  <span class="text-green-300 font-mono text-xs">1位${t.rank1_count || 0}</span>
                  <span class="text-blue-300 font-mono text-xs">2位${t.rank2_count || 0}</span>
                  <span class="text-gray-400 font-mono text-xs">/${t.picks}戦</span>
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

  // 出現する全ブロウラー (sorted) + JP名マップ
  const brawlerJp = {};  // EN → JP
  for (const t of m.all_trios) {
    for (const mem of t.members) brawlerJp[mem.brawler] = mem.brawler_jp || mem.brawler;
  }
  const brawlers = Object.keys(brawlerJp).sort((a, b) =>
    brawlerJp[a].localeCompare(brawlerJp[b], "ja")
  );

  const opt = (val, sel) => {
    const display = brawlerJp[val] || val;
    return `<option value="${escapeHtml(val)}" ${val === sel ? "selected" : ""}>${escapeHtml(display)}</option>`;
  };
  const dropdown = (slot, selected) => `
    <select onchange="setSynergyPick(${slot}, this.value)" class="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm max-w-full">
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
                <span class="text-xs sm:text-sm">${escapeHtml(mem.brawler_jp || mem.brawler)}</span>
              </div>
            `).join("")}
          </div>
          <div class="text-sm whitespace-nowrap ml-2 flex items-center gap-2">
            <span class="font-mono font-bold ${wrColor}">${(t.win_rate * 100).toFixed(0)}%</span>
            <span class="text-green-300 font-mono text-xs">1位${t.rank1_count || 0}</span>
            <span class="text-blue-300 font-mono text-xs">2位${t.rank2_count || 0}</span>
            <span class="text-gray-400 font-mono text-xs">/${t.picks}戦</span>
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

// 各ブロウラーに 現プールでの統計値を付与
//   _bestTier: 全マップ中の最高ティア (1マップでも取れれば反映)
//   _avgTier:  全マップを picks 重み付け平均したティア (ソート/グルーピング用、これがメイン指標)
//   _weightedWr / _weightedAvgRank: 加重平均勝率/平均順位
//   _poolMapsCount: 現プールで掲載されているマップ数
function computeBrawlerExtras() {
  if (!DB || !DB.brawlers || !DB.maps) return;
  if (DB._brawlerExtrasComputed) return;
  const tierScore = { "S+": 5, "S": 4, "A": 3, "B": 2, "C": 1, "?": 0 };
  const stats = {};
  for (const m of DB.maps) {
    if (!m.in_pool || !m.tier_list) continue;
    for (const t of m.tier_list) {
      const s = stats[t.brawler] || (stats[t.brawler] = {
        tiers: [], picks: 0, top2_sum: 0, rank_sum: 0,
        score_weighted: 0, score_pick_total: 0,
      });
      s.tiers.push(t.tier);
      const pk = t.picks || 0;
      const ts = tierScore[t.tier] ?? 0;
      s.picks += pk;
      s.top2_sum += (t.win_rate || 0) * pk;
      s.rank_sum += (t.avg_rank || 0) * pk;
      s.score_weighted += ts * pk;
      s.score_pick_total += pk;
    }
  }
  for (const b of DB.brawlers) {
    const s = stats[b.name] || {
      tiers: [], picks: 0, top2_sum: 0, rank_sum: 0,
      score_weighted: 0, score_pick_total: 0,
    };
    let bestTier = null;
    for (const t of s.tiers) {
      if (bestTier == null || (TIER_ORDER.indexOf(t) >= 0 && TIER_ORDER.indexOf(t) < TIER_ORDER.indexOf(bestTier))) {
        bestTier = t;
      }
    }
    b._bestTier = bestTier;

    // 加重平均ティア (継続的な強さ)
    let avgTier = null;
    if (s.score_pick_total > 0) {
      const avgScore = s.score_weighted / s.score_pick_total;
      if (avgScore >= 4.5) avgTier = "S+";
      else if (avgScore >= 3.5) avgTier = "S";
      else if (avgScore >= 2.5) avgTier = "A";
      else if (avgScore >= 1.5) avgTier = "B";
      else avgTier = "C";
    }
    b._avgTier = avgTier;

    b._weightedWr = s.picks ? (s.top2_sum / s.picks) : null;
    b._weightedAvgRank = s.picks ? (s.rank_sum / s.picks) : null;
    b._poolPicks = s.picks;
    b._poolMapsCount = s.tiers.length;
  }
  DB._brawlerExtrasComputed = true;
}

function renderBrawlerCard(b) {
  // ピンポイント強キャラの目印として best と avg が違う場合のみ best を小さく表示
  const tier = b._bestTier;
  const showPeak = tier && tier !== b._avgTier;
  const tierBadge = showPeak
    ? `<span class="absolute top-0 left-0 px-1 rounded-br text-[8px] font-bold ${TIER_COLORS[tier] || ''}" title="ピーク: ${tier}">${tier}</span>`
    : '';
  const wr = b._weightedWr;
  const wrColor = wr == null ? "text-gray-500"
    : wr >= 0.6 ? "text-green-300 font-bold"
    : wr >= 0.5 ? "text-yellow-300"
    : wr >= 0.4 ? "text-gray-300"
    : "text-red-300";
  const wrText = wr == null ? "—" : `${(wr * 100).toFixed(0)}%`;
  const dim = wr == null ? "opacity-60" : "";
  return `
    <div class="brawler-card relative p-0.5 bg-gray-800 hover:bg-gray-700 cursor-pointer rounded text-center border border-transparent hover:border-blue-500 ${dim}" data-name="${escapeHtml(b.name)}">
      ${tierBadge}
      ${b.image_url ? `<img src="${b.image_url}" class="w-full rounded">` : '<div class="w-full aspect-square bg-gray-700 rounded"></div>'}
      <div class="text-[10px] mt-0.5 truncate font-semibold leading-tight px-0.5">${escapeHtml(b.name_jp || b.name)}</div>
      <div class="text-[9px] ${wrColor} leading-tight">${wrText}</div>
    </div>`;
}

function renderBrawlerGrid(filter = "") {
  computeBrawlerExtras();
  const el = document.getElementById("brawler-grid");
  const f = (filter || "").toLowerCase();
  const sort = document.getElementById("brawler-sort")?.value || "best_tier";
  const strongOnly = document.getElementById("brawler-filter-strong")?.checked || false;

  let list = DB.brawlers.filter(b =>
    !f || b.name.toLowerCase().includes(f) || (b.name_jp || "").includes(filter)
  );
  if (strongOnly) {
    list = list.filter(b => b._avgTier === "S+" || b._avgTier === "S");
  }

  const tierIdx = t => {
    const i = TIER_ORDER.indexOf(t);
    return i < 0 ? 99 : i;
  };
  list.sort((a, b) => {
    if (sort === "best_tier") {
      const d = tierIdx(a._avgTier) - tierIdx(b._avgTier);
      if (d !== 0) return d;
      return (b._poolPicks || 0) - (a._poolPicks || 0);
    }
    if (sort === "weighted_wr") return (b._weightedWr || 0) - (a._weightedWr || 0);
    if (sort === "weighted_avg_rank") return (a._weightedAvgRank ?? 99) - (b._weightedAvgRank ?? 99);
    if (sort === "picks") return (b.total_picks || 0) - (a.total_picks || 0);
    if (sort === "name") return (a.name_jp || a.name).localeCompare(b.name_jp || b.name, "ja");
    return 0;
  });

  document.getElementById("brawler-count").textContent =
    `${list.length}体表示中 (全${DB.brawlers.length}体)`;

  // 現プール内 (_avgTier !== null) と プール外を分離
  const inPool = list.filter(b => b._avgTier);
  const outPool = list.filter(b => !b._avgTier);

  const gridCls = "grid grid-cols-5 sm:grid-cols-8 md:grid-cols-10 lg:grid-cols-12 xl:grid-cols-16 gap-1";

  let html = "";

  if (sort === "best_tier" && !filter) {
    // ティア別セクション分け (加重平均ティアでグループ化)
    const groups = {};
    for (const b of inPool) {
      const t = b._avgTier;
      (groups[t] ||= []).push(b);
    }
    for (const t of TIER_ORDER) {
      const g = groups[t];
      if (!g || g.length === 0) continue;
      html += `
        <div class="mb-3">
          <div class="flex items-baseline gap-2 mb-1.5 sticky top-0 bg-gray-900 py-1 z-[5]">
            <span class="px-2 py-0.5 rounded text-xs font-bold ${TIER_COLORS[t] || ''}">${t}</span>
            <span class="text-xs text-gray-400">${g.length}体</span>
          </div>
          <div class="${gridCls}">${g.map(renderBrawlerCard).join("")}</div>
        </div>`;
    }
  } else {
    html += `<div class="${gridCls}">${inPool.map(renderBrawlerCard).join("")}</div>`;
  }

  // プール外セクション (折りたたみ、デフォルト閉じる)
  if (outPool.length > 0 && !strongOnly) {
    html += `
      <details class="mt-4">
        <summary class="cursor-pointer text-sm text-gray-400 hover:text-gray-200 py-2 select-none">
          現プール未収録 ${outPool.length}体 (クリックで展開)
        </summary>
        <div class="${gridCls} mt-2">${outPool.map(renderBrawlerCard).join("")}</div>
      </details>`;
  }

  el.innerHTML = html;

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
  const dispName = b.name_jp || b.name;
  // PC・モバイルとも詳細にスクロール
  setTimeout(() => el.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  el.innerHTML = `
    <div class="bg-gray-800 p-6 rounded">
      <div class="flex items-center mb-6">
        ${b.image_url ? `<img src="${b.image_url}" class="w-20 h-20 rounded mr-4">` : ""}
        <div>
          <h2 class="text-2xl font-bold">${escapeHtml(dispName)}</h2>
          ${b.name_jp ? `<div class="text-xs text-gray-500">${escapeHtml(b.name)}</div>` : ""}
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
                <span>${escapeHtml(m.map_jp || m.map)}</span>
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
                <span>${escapeHtml(m.map_jp || m.map)}</span>
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
  const search = document.getElementById("brawler-search");
  const sort = document.getElementById("brawler-sort");
  const strong = document.getElementById("brawler-filter-strong");
  const trigger = () => renderBrawlerGrid(search.value);
  search.addEventListener("input", trigger);
  sort.addEventListener("change", trigger);
  strong.addEventListener("change", trigger);
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

// ============================================================
// マイページ機能
// ============================================================

// EN→JP マッピングを DB から構築
function buildBrawlerJpMap() {
  const map = {};
  if (!DB || !DB.brawlers) return map;
  for (const b of DB.brawlers) {
    map[b.name] = b.name_jp || b.name;
  }
  return map;
}

function buildBrawlerImgMap() {
  const map = {};
  if (!DB || !DB.brawlers) return map;
  for (const b of DB.brawlers) {
    if (b.image_url) map[b.name] = b.image_url;
  }
  return map;
}

// マップ EN → JP マッピング
function buildMapJpMap() {
  const map = {};
  if (!DB || !DB.maps) return map;
  for (const m of DB.maps) {
    map[m.name] = m.name_jp || m.name;
  }
  return map;
}

function setupMypage() {
  const tagInput = document.getElementById("mypage-tag");
  const searchBtn = document.getElementById("mypage-search");
  const refreshBtn = document.getElementById("mypage-refresh");

  // localStorage から復元
  const saved = localStorage.getItem("mypage_tag");
  if (saved) tagInput.value = saved;

  searchBtn.addEventListener("click", () => fetchMypage(tagInput.value));
  tagInput.addEventListener("keydown", e => {
    if (e.key === "Enter") fetchMypage(tagInput.value);
  });
  refreshBtn.addEventListener("click", () => refreshMypage(tagInput.value));
}

function normalizeTag(t) {
  t = (t || "").trim().toUpperCase().replace(/\s/g, "");
  if (!t) return "";
  if (!t.startsWith("#")) t = "#" + t;
  return t;
}

async function fetchMypage(rawTag, options = {}) {
  const tag = normalizeTag(rawTag);
  if (!tag || tag.length < 4) {
    renderMypageError("タグを入力してください (例: #YQ8YY09R)");
    return;
  }
  localStorage.setItem("mypage_tag", tag);
  document.getElementById("mypage-tag").value = tag;
  if (!options.pageOnly) {
    MYPAGE_BATTLES_PAGE = 1;  // 新規検索/更新時は1ページ目に戻す
  }
  renderMypageLoading(options.refresh ? "更新中..." : options.pageOnly ? "ページ切替中..." : "読込中...");
  try {
    const encTag = encodeURIComponent(tag);
    const offset = (MYPAGE_BATTLES_PAGE - 1) * MYPAGE_BATTLES_PER_PAGE;
    const battlesUrl = `${API_HOST}/api/player/${encTag}/battles?limit=${MYPAGE_BATTLES_PER_PAGE}&offset=${offset}`;
    const statsUrl = `${API_HOST}/api/player/${encTag}?period=${encodeURIComponent(MYPAGE_PERIOD)}`;
    const requests = options.pageOnly
      ? [Promise.resolve(null), fetch(battlesUrl)]
      : [fetch(statsUrl), fetch(battlesUrl)];
    const [statsRes, battlesRes] = await Promise.all(requests);
    if (!options.pageOnly) {
      if (!statsRes.ok) {
        const body = await statsRes.json().catch(() => ({ detail: statsRes.statusText }));
        throw new Error(body.detail || `HTTP ${statsRes.status}`);
      }
      MYPAGE_DATA = await statsRes.json();
    }
    if (battlesRes && battlesRes.ok) {
      const bj = await battlesRes.json();
      MYPAGE_DATA.battles = bj.battles || [];
      MYPAGE_BATTLES_TOTAL = bj.total || 0;
    } else {
      MYPAGE_DATA.battles = [];
      MYPAGE_BATTLES_TOTAL = 0;
    }
    renderMypage();
  } catch (e) {
    renderMypageError(`取得失敗: ${e.message}`);
  }
}

function changeBattlesPage(page) {
  const totalPages = Math.max(1, Math.ceil(MYPAGE_BATTLES_TOTAL / MYPAGE_BATTLES_PER_PAGE));
  if (page < 1) page = 1;
  if (page > totalPages) page = totalPages;
  if (page === MYPAGE_BATTLES_PAGE) return;
  MYPAGE_BATTLES_PAGE = page;
  fetchMypage(MYPAGE_DATA.tag, { pageOnly: true });
  // スクロールで履歴セクションへ
  setTimeout(() => {
    const el = document.getElementById("mypage-battle-list");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 100);
}

async function refreshMypage(rawTag) {
  const tag = normalizeTag(rawTag);
  if (!tag) return;
  const refreshBtn = document.getElementById("mypage-refresh");
  refreshBtn.disabled = true;
  refreshBtn.textContent = "更新中...";
  try {
    const url = `${API_HOST}/api/player/${encodeURIComponent(tag)}/refresh`;
    const res = await fetch(url, { method: "POST" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    // 更新後はGETで再取得
    await fetchMypage(tag);
  } catch (e) {
    renderMypageError(`更新失敗: ${e.message}`);
    refreshBtn.disabled = false;
    refreshBtn.textContent = "更新";
  }
}

function renderMypageLoading(msg) {
  document.getElementById("mypage-detail").innerHTML = `
    <div class="bg-gray-800 p-6 rounded text-center text-gray-400">
      ${escapeHtml(msg)}
    </div>`;
  document.getElementById("mypage-refresh").classList.add("hidden");
}

function renderMypageError(msg) {
  document.getElementById("mypage-detail").innerHTML = `
    <div class="bg-red-900/30 border border-red-700 p-4 rounded text-red-200">
      ${escapeHtml(msg)}
    </div>`;
}

function renderMypage() {
  if (!MYPAGE_DATA) return;
  const el = document.getElementById("mypage-detail");
  const d = MYPAGE_DATA;
  const stats = d.stats || {};
  const summary = stats.summary || {};
  const profile = d.profile || {};
  const brawlerJp = buildBrawlerJpMap();
  const brawlerImg = buildBrawlerImgMap();
  const mapJp = buildMapJpMap();

  const total = summary.total || 0;
  const top2 = summary.top2 || 0;
  const rank1 = summary.rank1 || 0;
  const top2Rate = total ? (top2 / total * 100) : 0;
  const rank1Rate = total ? (rank1 / total * 100) : 0;
  const avgRank = summary.avg_rank || 0;

  // 期間
  let period = "—";
  if (summary.first_battle && summary.last_battle) {
    const f = new Date(summary.first_battle.replace(/(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2}).*/, "$1-$2-$3T$4:$5:$6Z"));
    const l = new Date(summary.last_battle.replace(/(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2}).*/, "$1-$2-$3T$4:$5:$6Z"));
    const days = Math.max(1, Math.round((l - f) / 86400000));
    period = `${f.toLocaleDateString("ja-JP")} 〜 ${l.toLocaleDateString("ja-JP")} (${days}日間)`;
  }

  // 全体メタ参照: ブロウラー名 → 全マップ平均勝率 (DB.brawlers の集計から)
  const globalBrawlerStats = {};
  if (DB && DB.brawlers) {
    for (const b of DB.brawlers) {
      let wPick = 0, wWin = 0;
      for (const m of [...(b.best_maps || []), ...(b.worst_maps || [])]) {
        wPick += m.picks || 0;
        wWin += (m.win_rate || 0) * (m.picks || 0);
      }
      globalBrawlerStats[b.name] = {
        win_rate: wPick > 0 ? wWin / wPick : null,
        total_picks: b.total_picks || 0,
      };
    }
  }

  // クールダウンUI
  document.getElementById("mypage-refresh").classList.remove("hidden");
  startCooldownTimer(d.cooldown_seconds || 0);

  el.innerHTML = `
    ${renderMypageHeader(d, profile, period)}
    ${total === 0 ? renderEmptyState() : `
      ${renderMypageSummary(total, top2, top2Rate, rank1, rank1Rate, avgRank)}
      ${renderMypageHeatmap(d.battles || [], brawlerImg)}
      ${renderMypageBattleList(d.battles || [], brawlerImg, brawlerJp, mapJp)}
      ${renderMypageBrawlers(stats.brawlers || [], brawlerJp, brawlerImg, globalBrawlerStats, total)}
      ${renderMypageMaps(stats.maps || [], mapJp)}
      ${renderMypageRecommendations(stats.brawlers || [], brawlerJp, brawlerImg, globalBrawlerStats)}
    `}
    <div class="text-xs text-gray-500 mt-4 text-center">
      ウォッチリスト ${d.watchlist_count}/${d.watchlist_max} ・
      ${d.last_fetched_at ? `最終取得: ${new Date(d.last_fetched_at * 1000).toLocaleString("ja-JP")}` : "未取得"}
    </div>`;
}

function renderMypageHeader(d, profile, period) {
  const regAt = profile.registered_at
    ? new Date(profile.registered_at * 1000).toLocaleDateString("ja-JP")
    : "—";
  const periods = [
    { val: "1d", label: "1日" },
    { val: "7d", label: "7日" },
    { val: "30d", label: "30日" },
    { val: "all", label: "全期間" },
  ];
  const periodBtns = periods.map(p => {
    const active = MYPAGE_PERIOD === p.val;
    return `<button onclick="changeMypagePeriod('${p.val}')" class="px-3 py-1 rounded text-xs font-bold ${active ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}">${p.label}</button>`;
  }).join("");
  return `
    <div class="bg-gray-800 p-4 rounded mb-4">
      <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h2 class="text-xl font-bold">${escapeHtml(profile.name || d.tag)}</h2>
        <span class="text-sm text-gray-400 font-mono">${escapeHtml(d.tag)}</span>
        ${profile.trophies ? `<span class="text-sm text-yellow-400">🏆 ${profile.trophies.toLocaleString()}</span>` : ""}
      </div>
      <div class="text-xs text-gray-500 mt-1">
        登録: ${regAt} ・ データ期間: ${period}
      </div>
      <div class="flex flex-wrap gap-1 mt-3">
        <span class="text-xs text-gray-400 mr-1 self-center">集計期間:</span>
        ${periodBtns}
      </div>
    </div>`;
}

function changeMypagePeriod(p) {
  if (MYPAGE_PERIOD === p) return;
  MYPAGE_PERIOD = p;
  localStorage.setItem("mypage_period", p);
  if (MYPAGE_DATA && MYPAGE_DATA.tag) {
    fetchMypage(MYPAGE_DATA.tag);
  }
}

function renderEmptyState() {
  return `
    <div class="bg-yellow-900/30 border border-yellow-700 p-4 rounded text-yellow-200">
      まだトリオサバイバルの試合データがありません。<br>
      <span class="text-sm text-yellow-300">プレイ後、30分ごとに自動取得されます。「更新」ボタンで即時取得もできます。</span>
    </div>`;
}

function renderMypageSummary(total, top2, top2Rate, rank1, rank1Rate, avgRank) {
  return `
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
      <div class="bg-gray-800 p-3 rounded text-center">
        <div class="text-2xl font-bold">${total.toLocaleString()}</div>
        <div class="text-xs text-gray-400">総試合数</div>
      </div>
      <div class="bg-gray-800 p-3 rounded text-center">
        <div class="text-2xl font-bold text-green-400">${rank1Rate.toFixed(1)}%</div>
        <div class="text-xs text-gray-400">1位率 (${rank1})</div>
      </div>
      <div class="bg-gray-800 p-3 rounded text-center">
        <div class="text-2xl font-bold text-blue-400">${top2Rate.toFixed(1)}%</div>
        <div class="text-xs text-gray-400">TOP2率 (${top2})</div>
      </div>
      <div class="bg-gray-800 p-3 rounded text-center">
        <div class="text-2xl font-bold">${avgRank.toFixed(2)}</div>
        <div class="text-xs text-gray-400">平均順位</div>
      </div>
    </div>`;
}

// ティア帯ごとの色 (Brawl Insights の薄い色帯ほぼ準拠)
function rankBorderClass(rank) {
  if (rank === 1) return "ring-2 ring-green-500 bg-green-900/20";
  if (rank === 2) return "ring-2 ring-blue-400 bg-blue-900/20";
  if (rank === 3) return "ring-2 ring-gray-500 bg-gray-700/30";
  return "ring-2 ring-red-500 bg-red-900/20";  // rank 4
}

function rankLabel(rank) {
  if (rank === 1) return { text: "1位", color: "text-green-400" };
  if (rank === 2) return { text: "2位", color: "text-blue-300" };
  if (rank === 3) return { text: "3位", color: "text-gray-300" };
  return { text: "4位", color: "text-red-400" };
}

function formatBattleTime(bt) {
  // "20260503T154812.000Z" → Date
  const m = bt.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})/);
  if (!m) return { abs: bt, rel: "" };
  const d = new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`);
  const now = Date.now();
  const diffMin = Math.floor((now - d.getTime()) / 60000);
  let rel = "";
  if (diffMin < 1) rel = "たった今";
  else if (diffMin < 60) rel = `${diffMin}分前`;
  else if (diffMin < 1440) rel = `${Math.floor(diffMin / 60)}時間前`;
  else rel = `${Math.floor(diffMin / 1440)}日前`;
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  const yest = new Date(today.getTime() - 86400000);
  const isYest = d.toDateString() === yest.toDateString();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  let abs = "";
  if (isToday) abs = `今日 ${hh}:${mm}`;
  else if (isYest) abs = `昨日 ${hh}:${mm}`;
  else abs = `${d.getMonth() + 1}/${d.getDate()} ${hh}:${mm}`;
  return { abs, rel };
}

function renderMypageHeatmap(battles, brawlerImg) {
  if (battles.length === 0) return "";
  // 勝/分/敗カウント (1-2位=勝、3位=分、4位=敗)
  let win = 0, draw = 0, lose = 0;
  for (const b of battles) {
    if (b.rank <= 2) win++;
    else if (b.rank === 3) draw++;
    else lose++;
  }
  const winRate = battles.length ? (win / battles.length * 100) : 0;

  const rankBadgeBg = { 1: "bg-green-600", 2: "bg-blue-500", 3: "bg-gray-500", 4: "bg-red-600" };
  const cells = battles.map(b => {
    const cls = rankBorderClass(b.rank);
    const brawler = b.brawler || "";
    const img = brawlerImg[brawler];
    const tcSign = b.trophy_change >= 0 ? '+' : '';
    const rankBg = rankBadgeBg[b.rank] || "bg-gray-700";
    return `<div class="aspect-square rounded ${cls} relative flex items-center justify-center" title="${escapeHtml(brawler)} ${b.rank}位 (${tcSign}${b.trophy_change})">
      ${img ? `<img src="${img}" class="w-full h-full rounded object-cover" loading="lazy">` : `<span class="text-[10px]">${escapeHtml(brawler.slice(0, 3))}</span>`}
      <span class="absolute bottom-0 right-0 ${rankBg} text-white text-[10px] font-bold leading-none px-1 py-0.5 rounded-tl rounded-br">${b.rank}</span>
    </div>`;
  }).join("");

  const showingFrom = (MYPAGE_BATTLES_PAGE - 1) * MYPAGE_BATTLES_PER_PAGE + 1;
  const showingTo = showingFrom + battles.length - 1;
  const headerLabel = MYPAGE_BATTLES_TOTAL > MYPAGE_BATTLES_PER_PAGE
    ? `試合 ${showingFrom}-${showingTo}`
    : `直近${battles.length}試合`;

  return `
    <div class="bg-gray-800 p-4 rounded mb-4">
      <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-3">
        <h3 class="text-sm font-bold text-gray-300 uppercase tracking-wide">${escapeHtml(headerLabel)}</h3>
        <span class="text-sm">
          <span class="text-green-400 font-bold">${win}勝</span>
          <span class="text-gray-400 mx-1">${draw}分</span>
          <span class="text-red-400 font-bold">${lose}敗</span>
          <span class="ml-2 font-mono text-yellow-300">勝率 ${winRate.toFixed(1)}%</span>
        </span>
      </div>
      <div class="grid grid-cols-10 gap-1">
        ${cells}
      </div>
      <div class="text-xs text-gray-500 mt-2 flex flex-wrap gap-3">
        <span><span class="inline-block w-3 h-3 rounded ring-2 ring-green-500"></span> 1位</span>
        <span><span class="inline-block w-3 h-3 rounded ring-2 ring-blue-400"></span> 2位</span>
        <span><span class="inline-block w-3 h-3 rounded ring-2 ring-gray-500"></span> 3位</span>
        <span><span class="inline-block w-3 h-3 rounded ring-2 ring-red-500"></span> 4位</span>
      </div>
    </div>`;
}

function renderTeam(members, brawlerImg, brawlerJp, highlightTag) {
  return `<div class="flex items-center gap-1">
    ${members.map(m => {
      const img = brawlerImg[m.brawler];
      const isMe = m.tag === highlightTag;
      return `<div class="flex items-center gap-1 px-1 py-0.5 rounded ${isMe ? 'bg-yellow-700/30 ring-1 ring-yellow-500' : 'bg-gray-700/40'}">
        ${img ? `<img src="${img}" class="w-6 h-6 rounded" loading="lazy">` : ""}
        <div class="text-xs leading-tight">
          <div class="truncate max-w-[70px]">${escapeHtml(m.name || m.brawler)}</div>
          <div class="text-[10px] text-gray-400">🏆${m.trophies}</div>
        </div>
      </div>`;
    }).join("")}
  </div>`;
}

function renderMypageBattleList(battles, brawlerImg, brawlerJp, mapJp) {
  if (battles.length === 0 && MYPAGE_BATTLES_TOTAL === 0) return "";
  const myTag = MYPAGE_DATA?.tag || "";
  const cards = battles.map(b => {
    const lbl = rankLabel(b.rank);
    const t = formatBattleTime(b.battle_time);
    const tc = b.trophy_change;
    const tcStr = tc > 0 ? `+${tc}` : tc < 0 ? `${tc}` : "±0";
    const tcColor = tc > 0 ? "text-green-400" : tc < 0 ? "text-red-400" : "text-gray-400";
    const cardBg = b.rank === 1 ? "bg-green-900/15 border-green-700/50"
      : b.rank === 2 ? "bg-blue-900/10 border-blue-700/40"
      : b.rank === 3 ? "bg-gray-700/20 border-gray-600/40"
      : "bg-red-900/15 border-red-700/50";

    return `<div class="border rounded p-2 ${cardBg}">
      <div class="flex items-center justify-between mb-2 text-sm">
        <div class="flex items-center gap-2">
          <span class="font-bold ${lbl.color}">${lbl.text}</span>
          <span class="font-mono ${tcColor} text-xs">${tcStr}</span>
        </div>
        <div class="text-xs text-gray-400 truncate ml-2">
          ${escapeHtml(mapJp[b.map] || b.map || b.mode)} · ${t.abs} <span class="text-gray-600">(${t.rel})</span>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <div class="text-xs text-gray-400 w-10">味方</div>
        ${renderTeam(b.my_team, brawlerImg, brawlerJp, myTag)}
      </div>
      <div class="flex flex-wrap items-start gap-2 mt-1">
        <div class="text-xs text-gray-400 w-10">vs</div>
        <div class="flex flex-wrap gap-2">
          ${b.enemy_teams.map(t => renderTeam(t, brawlerImg, brawlerJp, myTag)).join('<span class="text-gray-600 text-xs self-center">/</span>')}
        </div>
      </div>
    </div>`;
  }).join("");

  return `
    <div id="mypage-battle-list" class="bg-gray-800 p-4 rounded mb-4">
      <div class="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <h3 class="text-sm font-bold text-gray-300 uppercase tracking-wide">試合履歴</h3>
        <span class="text-xs text-gray-400">累計 ${MYPAGE_BATTLES_TOTAL.toLocaleString()}戦</span>
      </div>
      ${renderBattlesPagination()}
      <div class="space-y-2 mt-3">${cards}</div>
      <div class="mt-3">${renderBattlesPagination()}</div>
    </div>`;
}

function renderBattlesPagination() {
  const total = MYPAGE_BATTLES_TOTAL;
  const per = MYPAGE_BATTLES_PER_PAGE;
  const totalPages = Math.max(1, Math.ceil(total / per));
  if (totalPages <= 1) return "";
  const cur = MYPAGE_BATTLES_PAGE;

  // ページ番号ボタンの可視範囲: 現在±2 + 先頭/末尾
  const visible = new Set([1, totalPages, cur, cur - 1, cur + 1, cur - 2, cur + 2]);
  const pages = [...visible].filter(p => p >= 1 && p <= totalPages).sort((a, b) => a - b);

  let html = "";
  let prev = 0;
  for (const p of pages) {
    if (prev && p - prev > 1) html += `<span class="px-2 text-gray-500">…</span>`;
    const active = p === cur;
    html += `<button onclick="changeBattlesPage(${p})" class="px-3 py-1 rounded text-sm ${active ? 'bg-blue-600 text-white font-bold' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}">${p}</button>`;
    prev = p;
  }
  const showingFrom = (cur - 1) * per + 1;
  const showingTo = Math.min(cur * per, total);
  return `<div class="flex flex-wrap items-center gap-1 text-sm">
    <button onclick="changeBattlesPage(${cur - 1})" class="px-2 py-1 rounded ${cur === 1 ? 'bg-gray-800 text-gray-600 cursor-not-allowed' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}" ${cur === 1 ? 'disabled' : ''}>‹</button>
    ${html}
    <button onclick="changeBattlesPage(${cur + 1})" class="px-2 py-1 rounded ${cur === totalPages ? 'bg-gray-800 text-gray-600 cursor-not-allowed' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}" ${cur === totalPages ? 'disabled' : ''}>›</button>
    <span class="text-xs text-gray-500 ml-2">${showingFrom}-${showingTo} / ${total.toLocaleString()}</span>
  </div>`;
}

function renderMypageBrawlers(brawlers, brawlerJp, brawlerImg, globalStats, totalPicks) {
  if (brawlers.length === 0) return "";
  const rows = brawlers.map(b => {
    const myWr = b.picks ? (b.top2 / b.picks) : 0;
    const gs = globalStats[b.brawler];
    let diffHtml = '<span class="text-gray-500">—</span>';
    if (gs && gs.win_rate != null) {
      const diff = (myWr - gs.win_rate) * 100;
      const color = diff > 5 ? "text-green-400" : diff < -5 ? "text-red-400" : "text-gray-300";
      const sign = diff >= 0 ? "+" : "";
      diffHtml = `<span class="${color} font-mono">${sign}${diff.toFixed(1)}pt</span>`;
    }
    const pickRate = totalPicks ? (b.picks / totalPicks * 100) : 0;
    return `<tr class="border-b border-gray-700/50 hover:bg-gray-700/30">
      <td class="py-2 px-2">
        <div class="flex items-center">
          ${brawlerImg[b.brawler] ? `<img src="${brawlerImg[b.brawler]}" class="w-7 h-7 mr-2 rounded">` : ""}
          <span>${escapeHtml(brawlerJp[b.brawler] || b.brawler)}</span>
        </div>
      </td>
      <td class="py-2 px-2 text-right font-mono">${b.picks}</td>
      <td class="py-2 px-2 text-right font-mono text-gray-400 text-xs hidden sm:table-cell">${pickRate.toFixed(1)}%</td>
      <td class="py-2 px-2 text-right font-mono text-green-300">${(b.rank1 / b.picks * 100).toFixed(1)}%</td>
      <td class="py-2 px-2 text-right font-mono text-blue-300">${(b.top2 / b.picks * 100).toFixed(1)}%</td>
      <td class="py-2 px-2 text-right font-mono">${b.avg_rank.toFixed(2)}</td>
      <td class="py-2 px-2 text-right hidden md:table-cell">${diffHtml}</td>
    </tr>`;
  }).join("");
  return `
    <div class="bg-gray-800 p-4 rounded mb-4">
      <h3 class="text-sm font-bold mb-2 text-gray-300 uppercase tracking-wide">ブロウラー別 (試合数順)</h3>
      <div class="overflow-x-auto -mx-2">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-xs text-gray-400 border-b border-gray-700">
            <th class="pb-2 px-2">ブロウラー</th>
            <th class="pb-2 px-2 text-right">picks</th>
            <th class="pb-2 px-2 text-right hidden sm:table-cell">pick率</th>
            <th class="pb-2 px-2 text-right">1位率</th>
            <th class="pb-2 px-2 text-right">TOP2率</th>
            <th class="pb-2 px-2 text-right">平均順位</th>
            <th class="pb-2 px-2 text-right hidden md:table-cell">vs全体WR</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      </div>
    </div>`;
}

function renderMypageMaps(maps, mapJp) {
  if (maps.length === 0) return "";
  // ベスト3 / ワースト3 を抽出 (最低3戦以上で)
  const eligible = maps.filter(m => m.picks >= 3);
  const sorted = [...eligible].sort((a, b) => (b.top2 / b.picks) - (a.top2 / a.picks));
  const best = sorted.slice(0, 3);
  const worst = sorted.slice(-3).reverse();

  const renderRow = m => {
    const wr = (m.top2 / m.picks * 100);
    return `<div class="flex justify-between p-2 hover:bg-gray-700/50 rounded">
      <span class="truncate">${escapeHtml(mapJp[m.map] || m.map)}</span>
      <span class="text-sm font-mono whitespace-nowrap ml-2">${wr.toFixed(1)}% <span class="text-gray-500 text-xs">(${m.picks}戦)</span></span>
    </div>`;
  };

  return `
    <div class="bg-gray-800 p-4 rounded mb-4">
      <h3 class="text-sm font-bold mb-2 text-gray-300 uppercase tracking-wide">マップ別 TOP2率</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <h4 class="text-green-400 font-bold text-sm mb-1">強いマップ TOP3</h4>
          ${best.length ? best.map(renderRow).join("") : '<div class="text-gray-500 text-sm p-2">サンプル不足 (3戦以上必要)</div>'}
        </div>
        <div>
          <h4 class="text-red-400 font-bold text-sm mb-1">苦手なマップ TOP3</h4>
          ${worst.length ? worst.map(renderRow).join("") : '<div class="text-gray-500 text-sm p-2">サンプル不足</div>'}
        </div>
      </div>
      ${maps.length > 6 ? `
        <details class="mt-4">
          <summary class="cursor-pointer text-xs text-gray-400 hover:text-gray-200">全マップ ${maps.length}件を表示</summary>
          <div class="mt-2 space-y-1">${maps.map(renderRow).join("")}</div>
        </details>` : ""}
    </div>`;
}

function renderMypageRecommendations(myBrawlers, brawlerJp, brawlerImg, globalStats) {
  if (!DB || !DB.maps) return "";
  // 自分が使った全ブロウラー
  const usedSet = new Set(myBrawlers.map(b => b.brawler));
  // 全体メタで強いブロウラー (S+ / S) で、自分が一度も使ってないもの
  const sTierUnused = [];
  for (const m of DB.maps) {
    if (!m.in_pool || !m.tier_list) continue;
    for (const t of m.tier_list) {
      if (t.tier === "S+" || t.tier === "S") {
        if (!usedSet.has(t.brawler)) sTierUnused.push({
          brawler: t.brawler,
          map: m.name,
          map_jp: m.name_jp,
          tier: t.tier,
          win_rate: t.win_rate || 0,
        });
      }
    }
  }
  // ブロウラー単位で集約 (出現回数=どれだけ広く強いか)
  const agg = {};
  for (const x of sTierUnused) {
    if (!agg[x.brawler]) agg[x.brawler] = { count: 0, maps: [] };
    agg[x.brawler].count++;
    agg[x.brawler].maps.push({ map: x.map_jp || x.map, tier: x.tier, wr: x.win_rate });
  }
  const recos = Object.entries(agg)
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 10);

  if (recos.length === 0) return "";

  return `
    <div class="bg-gray-800 p-4 rounded mb-4">
      <h3 class="text-sm font-bold mb-2 text-gray-300 uppercase tracking-wide">レコメンド: 未使用の強キャラ</h3>
      <div class="text-xs text-gray-400 mb-2">あなたが一度も使っていない、現プールマップでS/S+ティアのブロウラー</div>
      <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
        ${recos.map(([name, info]) => `
          <div class="bg-gray-700/40 p-2 rounded text-center">
            ${brawlerImg[name] ? `<img src="${brawlerImg[name]}" class="w-12 h-12 mx-auto rounded">` : ""}
            <div class="text-sm font-semibold mt-1 truncate">${escapeHtml(brawlerJp[name] || name)}</div>
            <div class="text-xs text-gray-400">${info.count}マップで強い</div>
          </div>
        `).join("")}
      </div>
    </div>`;
}

function startCooldownTimer(initial) {
  if (MYPAGE_COOLDOWN_TIMER) {
    clearInterval(MYPAGE_COOLDOWN_TIMER);
    MYPAGE_COOLDOWN_TIMER = null;
  }
  const btn = document.getElementById("mypage-refresh");
  let remaining = initial;
  const update = () => {
    if (remaining <= 0) {
      btn.disabled = false;
      btn.textContent = "更新";
      btn.classList.remove("opacity-50", "cursor-not-allowed");
      if (MYPAGE_COOLDOWN_TIMER) {
        clearInterval(MYPAGE_COOLDOWN_TIMER);
        MYPAGE_COOLDOWN_TIMER = null;
      }
      return;
    }
    const m = Math.floor(remaining / 60);
    const s = remaining % 60;
    btn.disabled = true;
    btn.classList.add("opacity-50", "cursor-not-allowed");
    btn.textContent = `${m}:${String(s).padStart(2, "0")}後`;
    remaining--;
  };
  update();
  if (initial > 0) {
    MYPAGE_COOLDOWN_TIMER = setInterval(update, 1000);
  }
}

setupMypage();

// 上に戻るボタン
const scrollTopBtn = document.getElementById("scroll-top-btn");
if (scrollTopBtn) {
  window.addEventListener("scroll", () => {
    if (window.scrollY > 300) {
      scrollTopBtn.classList.remove("opacity-0", "pointer-events-none");
      scrollTopBtn.classList.add("opacity-100");
    } else {
      scrollTopBtn.classList.add("opacity-0", "pointer-events-none");
      scrollTopBtn.classList.remove("opacity-100");
    }
  }, { passive: true });
  scrollTopBtn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

load();
