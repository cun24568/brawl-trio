let DB = null;
let ROTATION = null;  // {cycle_days, anchor_date, rotation: [...]}
let currentMap = null;
let currentTierFilter = "all";  // all / S+ / S / A / B / C
let currentMapSection = localStorage.getItem("map_section") || "tier";  // tier | recommended | synergy
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
let MYPAGE_SECTION = localStorage.getItem("mypage_section") || "history";  // history | brawlers | maps | recommend | matchups
let MYPAGE_RECENT_STATS = null;  // 直近 vs 全期間 比較用 (7d snapshot)
let MYPAGE_BATTLES_FILTER = { brawler: "", map: "", rank: "" };  // 試合履歴フィルタ
let MYPAGE_MATCHUPS = null;  // マッチアップ分析データ

// ============================================================
// i18n (ja デフォルト、 en切替対応)
// ============================================================
function detectLang() {
  // ユーザーが明示的に選択した言語があればそれを優先
  const saved = localStorage.getItem("lang");
  if (saved === "ja" || saved === "en") return saved;
  // ブラウザの言語設定で判定: ja* → ja, それ以外 → en
  const browserLang = (navigator.language || "ja").toLowerCase();
  return browserLang.startsWith("ja") ? "ja" : "en";
}
let LANG = detectLang();
const I18N = {
  ja: {
    site_title: "ブロスタ トリオデータベース",
    nav_maps: "マップ別ティア",
    nav_brawlers: "ブロウラー別",
    nav_mypage: "マイページ",
    nav_club: "クラブ",
    nav_ranking: "ランキング",
    nav_roulette: "ルーレット",
    today: "今日",
    tomorrow: "明日",
    rot_label: "ローテ",
    last_update: "最終更新",
    total_battles: "集計",
    battles_unit: "戦",
    section_tier: "ティア表",
    section_recommended: "推奨編成",
    section_synergy: "シナジー検索",
    section_history: "試合履歴",
    section_brawlers: "ブロウラー別",
    section_maps: "マップ別",
    section_recommend: "レコメンド",
    section_matchups: "マッチアップ",
    period_1d: "1日",
    period_7d: "7日",
    period_30d: "30日",
    period_all: "全期間",
    period_label: "集計期間",
    summary_total: "総試合数",
    summary_rank1: "1位率",
    summary_top2: "TOP2率",
    summary_avg: "平均順位",
    filter_brawler: "ブロウラー",
    filter_map: "マップ",
    filter_rank: "順位",
    filter_all: "全部",
    filter_reset: "リセット",
    compare_period_recent: "直近7日",
    compare_period_all: "全期間",
    diff: "差分",
    win: "勝",
    draw: "分",
    lose: "敗",
    win_rate: "勝率",
    no_data: "データなし",
    loading: "読込中...",
    search: "検索",
    update: "更新",
    bookmark_count: "ブックマーク",
    matchup_my: "自分のブロウラー",
    matchup_enemy: "敵に居たブロウラー",
    matchup_seen: "対戦数",
    matchup_avg_rank: "平均順位",
    matchup_global: "全体: 苦手な敵 (avg_rank高)",
  },
  en: {
    site_title: "Brawl Trio Database",
    nav_maps: "Maps",
    nav_brawlers: "Brawlers",
    nav_mypage: "My Page",
    nav_club: "Club",
    nav_ranking: "Ranking",
    nav_roulette: "Roulette",
    today: "Today",
    tomorrow: "Tomorrow",
    rot_label: "Rotation",
    last_update: "Last update",
    total_battles: "Total",
    battles_unit: "battles",
    section_tier: "Tier list",
    section_recommended: "Recommended trios",
    section_synergy: "Synergy search",
    section_history: "Battle history",
    section_brawlers: "By brawler",
    section_maps: "By map",
    section_recommend: "Recommendations",
    section_matchups: "Matchups",
    period_1d: "1d",
    period_7d: "7d",
    period_30d: "30d",
    period_all: "All",
    period_label: "Period",
    summary_total: "Battles",
    summary_rank1: "1st rate",
    summary_top2: "Top2 rate",
    summary_avg: "Avg rank",
    filter_brawler: "Brawler",
    filter_map: "Map",
    filter_rank: "Rank",
    filter_all: "All",
    filter_reset: "Reset",
    compare_period_recent: "Recent 7d",
    compare_period_all: "All time",
    diff: "Diff",
    win: "W",
    draw: "D",
    lose: "L",
    win_rate: "Win rate",
    no_data: "No data",
    loading: "Loading...",
    search: "Search",
    update: "Refresh",
    bookmark_count: "Bookmarks",
    matchup_my: "Your brawler",
    matchup_enemy: "Enemy brawler",
    matchup_seen: "Seen",
    matchup_avg_rank: "Avg rank",
    matchup_global: "Overall: tough enemies (high avg_rank)",
  },
};
function t(key) {
  return (I18N[LANG] || I18N.ja)[key] || I18N.ja[key] || key;
}
function setLang(lang) {
  LANG = lang;
  localStorage.setItem("lang", lang);
  applyI18nStatic();
  // 動的レンダの再描画
  if (DB) {
    renderRotationBanner();
    renderMapList();
    if (currentMap) renderMapDetail();
    renderBrawlerGrid(document.getElementById("brawler-search")?.value || "");
  }
  if (MYPAGE_DATA) renderMypage();
}
function applyI18nStatic() {
  // <title>
  document.title = t("site_title");
  // h1
  const h1 = document.querySelector("header h1");
  if (h1) h1.textContent = t("site_title");
  // タブボタン (data-tab → label)
  const tabMap = {maps:"nav_maps", brawlers:"nav_brawlers", mypage:"nav_mypage", club:"nav_club", ranking:"nav_ranking", roulette:"nav_roulette"};
  document.querySelectorAll(".tab-btn").forEach(btn => {
    const k = tabMap[btn.dataset.tab];
    if (k) btn.textContent = t(k);
  });
  // 言語ボタンのactive状態
  const ja = document.getElementById("lang-ja");
  const en = document.getElementById("lang-en");
  if (ja && en) {
    ja.className = "px-2 py-1 rounded text-xs " + (LANG === "ja" ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-300");
    en.className = "px-2 py-1 rounded text-xs " + (LANG === "en" ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-300");
  }
}
// 初回適用
setTimeout(applyI18nStatic, 0);

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
    `${t("last_update")}: ${ts.toLocaleString(LANG === "en" ? "en-US" : "ja-JP")} / ${t("total_battles")} ${DB.stats.total_picks.toLocaleString()}${t("battles_unit")}`;
  renderRotationBanner();
  renderMapList();
  // 今日のマップを自動選択 (ローテ情報あれば)
  let initialMap = null;
  const candidates = DB._mapCandidates || DB.maps;
  if (ROTATION) {
    // 5時境界の影響を避けるため正午基準で評価
    const baseToday = new Date();
    if (baseToday.getHours() < 5) baseToday.setDate(baseToday.getDate() - 1);
    baseToday.setHours(12, 0, 0, 0);
    const todayJp = rotationMapForDate(baseToday);
    initialMap = candidates.find(m => (m.name_jp || m.name) === todayJp);
  }
  if (!initialMap) initialMap = candidates[0];
  if (initialMap) selectMap(initialMap);
  renderBrawlerGrid();
  setupTabs();
  setupSearch();
}

// ローテーション計算: 指定日付 (Date) のマップ名(JP)を返す
// マップ切替は毎日 5:00 のため、 5時前は前日扱い (5/6 04:59 → 5/5扱い、 5/6 05:00 → 5/6)
function rotationMapForDate(date) {
  if (!ROTATION) return null;
  const d = new Date(date);
  if (d.getHours() < 5) d.setDate(d.getDate() - 1);
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const anchor = new Date(ROTATION.anchor_date + "T00:00:00");
  const diffDays = Math.floor((target - anchor) / 86400000);
  const idx = ((diffDays % ROTATION.cycle_days) + ROTATION.cycle_days) % ROTATION.cycle_days;
  return ROTATION.rotation[idx];
}

// 指定マップ(JP名)の次回出現日を返す: {date: Date, daysAhead: number} or null
// 5時境界の影響を避けるため日付は 12時 で生成
function nextAppearance(mapJp) {
  if (!ROTATION) return null;
  const now = new Date();
  // 「今日」の起点も5時境界考慮: 5時前なら前日基準
  let baseDay = new Date(now);
  if (baseDay.getHours() < 5) baseDay.setDate(baseDay.getDate() - 1);
  for (let d = 0; d < ROTATION.cycle_days; d++) {
    const t = new Date(baseDay.getFullYear(), baseDay.getMonth(), baseDay.getDate() + d, 12);
    if (rotationMapForDate(t) === mapJp) return { date: t, daysAhead: d };
  }
  return null;
}

function renderRotationBanner() {
  const el = document.getElementById("rotation-banner");
  if (!el || !ROTATION) return;
  const now = new Date();
  // 5時境界: 5時前は前日扱い
  const baseToday = new Date(now);
  if (baseToday.getHours() < 5) baseToday.setDate(baseToday.getDate() - 1);
  baseToday.setHours(12, 0, 0, 0);
  const items = [];
  for (let d = 0; d < 2; d++) {
    const t = new Date(baseToday.getFullYear(), baseToday.getMonth(), baseToday.getDate() + d, 12);
    const map = rotationMapForDate(t);
    const label = d === 0 ? t("today") : t("tomorrow");
    const color = d === 0 ? "text-yellow-300 font-bold" : "text-gray-200";
    items.push(`<span class="${color}">${label}</span>: <span class="text-white font-semibold">${escapeHtml(map || "?")}</span>`);
  }
  el.innerHTML = `
    <div class="text-xs sm:text-sm text-gray-400 flex flex-wrap items-center gap-x-3 gap-y-1">
      <span class="text-gray-500">📅 ${t("rot_label")}</span>
      ${items.join('<span class="text-gray-600">·</span>')}
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
        ${renderMapSectionSelector()}
        ${currentMapSection === "tier" ? `
          ${filterButtons}
          <h3 class="text-sm font-bold mt-4 mb-2 text-gray-300 uppercase tracking-wide">ティアリスト ${currentTierFilter !== 'all' ? `(${currentTierFilter}のみ)` : ''}</h3>
          ${tableHtml}
        ` : ""}
        ${currentMapSection === "synergy" ? renderSynergySection(m) : ""}
        ${currentMapSection === "recommended" && m.recommended_trios && m.recommended_trios.length > 0 ? `
          <h3 class="text-sm font-bold mt-4 mb-2 text-gray-300 uppercase tracking-wide">推奨トリオ編成</h3>
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
        ${currentMapSection === "recommended" && (!m.recommended_trios || m.recommended_trios.length === 0) ? '<div class="text-gray-500 text-sm mt-4">推奨編成のデータが不足しています (3戦以上の組合せが必要)</div>' : ""}
      </div>
    </div>`;
}

function renderMapSectionSelector() {
  const sections = [
    { val: "tier", label: "ティア表" },
    { val: "recommended", label: "推奨編成" },
    { val: "synergy", label: "シナジー検索" },
  ];
  return `
    <div class="mt-3 mb-2">
      <select onchange="setMapSection(this.value)" class="w-full sm:w-auto p-2 bg-gray-900 border border-gray-700 rounded text-base">
        ${sections.map(s => `<option value="${s.val}" ${currentMapSection === s.val ? "selected" : ""}>${s.label}</option>`).join("")}
      </select>
    </div>`;
}

function setMapSection(s) {
  currentMapSection = s;
  localStorage.setItem("map_section", s);
  renderMapDetail();
}

// シナジー検索の名前検索 (ひらがな対応)。 入力中は setSynergyPick を呼ばない (再描画で入力が消えるため)
function onSynergySearchInput(slot, val) {
  const sug = document.getElementById(`synergy-suggest-${slot}`);
  if (!sug) return;
  if (!val) {
    sug.classList.add("hidden");
    return;
  }
  const m = currentMap;
  if (!m || !m.all_trios) { sug.classList.add("hidden"); return; }
  const brawlerJpMap = {};
  for (const t of m.all_trios) {
    for (const mem of t.members) brawlerJpMap[mem.brawler] = mem.brawler_jp || mem.brawler;
  }
  const matches = Object.entries(brawlerJpMap).filter(([en, jp]) => brawlerNameMatches(en, jp, val));
  if (matches.length === 0) {
    sug.innerHTML = '<div class="px-3 py-2 text-sm text-gray-500">該当なし</div>';
    sug.classList.remove("hidden");
    return;
  }
  matches.sort((a, b) => (a[1] || "").localeCompare(b[1] || "", "ja"));
  sug.innerHTML = matches.slice(0, 30).map(([en, jp]) => `
    <div onclick="selectSynergyMember(${slot}, '${escapeHtml(en)}')" class="px-3 py-2 text-sm cursor-pointer hover:bg-gray-700">
      ${escapeHtml(jp || en)} <span class="text-gray-500 text-xs">${escapeHtml(en)}</span>
    </div>`).join("");
  sug.classList.remove("hidden");
}

function selectSynergyMember(slot, en) {
  const sug = document.getElementById(`synergy-suggest-${slot}`);
  if (sug) sug.classList.add("hidden");
  setSynergyPick(slot, en);
}

// クリック外で synergy サジェスト閉じる (1度だけ登録)
if (typeof window._synergyCloseAttached === "undefined") {
  window._synergyCloseAttached = true;
  document.addEventListener("click", e => {
    for (const slot of [1, 2]) {
      const sug = document.getElementById(`synergy-suggest-${slot}`);
      const inp = document.getElementById(`synergy-input-${slot}`);
      if (sug && inp && !sug.contains(e.target) && e.target !== inp) {
        sug.classList.add("hidden");
      }
    }
  });
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

  const dropdown = (slot, selected) => {
    const display = brawlerJp[selected] || selected || "";
    return `<div class="relative">
      <input type="text" id="synergy-input-${slot}"
             value="${escapeHtml(display)}"
             placeholder="${slot}人目検索 (ひらがな可)"
             oninput="onSynergySearchInput(${slot}, this.value)"
             onfocus="onSynergySearchInput(${slot}, this.value)"
             autocomplete="off"
             class="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm w-44">
      <div id="synergy-suggest-${slot}" class="absolute top-full left-0 mt-1 bg-gray-800 border border-gray-700 rounded shadow-lg max-h-72 overflow-y-auto z-30 hidden min-w-[200px]"></div>
    </div>`;
  };

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
  const fHira = kanaToHira(f);
  const sort = document.getElementById("brawler-sort")?.value || "best_tier";
  const strongOnly = document.getElementById("brawler-filter-strong")?.checked || false;

  let list = DB.brawlers.filter(b => brawlerNameMatches(b.name, b.name_jp, filter));
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

// カタカナ→ひらがな変換 (ブロウラー名検索でひらがな入力にも対応するため)
function kanaToHira(s) {
  return String(s ?? "").replace(/[ァ-ヶ]/g, c => String.fromCharCode(c.charCodeAt(0) - 0x60));
}

// ブロウラー名検索エイリアス (英語表記のまま日本語名になってるキャラを 日本語読みでも検索可に)
// キーは大文字 + 記号/空白除去で正規化したもの
const BRAWLER_ALIASES = {
  "MAX": ["マックス", "まっくす"],
  "EMZ": ["イーエムジー", "えむず", "エムズ", "イーエム", "え", "エ"],
  "8BIT": ["エイトビット", "8ビット", "えいとびっと"],
  "RT": ["アールティー", "アール", "あーるてぃー"],
  "MRP": ["ミスターP", "ミスターピー", "みすたーぴー", "ぴー", "ピー", "p"],
};

function _aliasKey(s) {
  return (s || "").toUpperCase().replace(/[\s.\-]/g, "");
}

function brawlerNameMatches(enName, jpName, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  const qHira = kanaToHira(q);
  if (enName && enName.toLowerCase().includes(q)) return true;
  if (jpName) {
    if (jpName.includes(query)) return true;
    if (kanaToHira(jpName.toLowerCase()).includes(qHira)) return true;
  }
  const aliases = BRAWLER_ALIASES[_aliasKey(enName)] || [];
  for (const a of aliases) {
    if (a.toLowerCase().includes(q)) return true;
    if (kanaToHira(a.toLowerCase()).includes(qHira)) return true;
  }
  return false;
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
  const bookmarkBtn = document.getElementById("mypage-bookmark");
  const suggest = document.getElementById("mypage-suggest");

  // localStorage から復元
  const saved = localStorage.getItem("mypage_tag");
  if (saved) tagInput.value = saved;

  searchBtn.addEventListener("click", () => {
    hideSuggest(suggest);
    fetchMypage(tagInput.value);
  });
  tagInput.addEventListener("keydown", e => {
    if (e.key === "Enter") {
      hideSuggest(suggest);
      fetchMypage(tagInput.value);
    } else if (e.key === "Escape") {
      hideSuggest(suggest);
    }
  });
  attachNameSuggest(tagInput, suggest, "players", item => {
    tagInput.value = item.tag;
    hideSuggest(suggest);
    fetchMypage(item.tag);
  });
  refreshBtn.addEventListener("click", () => refreshMypage(tagInput.value));
  bookmarkBtn.addEventListener("click", () => toggleCurrentBookmark());
  renderBookmarks();
}

// ============================================================
// ブックマーク機能 (localStorage、 最大50件)
// ============================================================

function getBookmarks() {
  try { return JSON.parse(localStorage.getItem("mypage_bookmarks") || "[]"); }
  catch { return []; }
}
function setBookmarksAndRender(bms) {
  localStorage.setItem("mypage_bookmarks", JSON.stringify(bms.slice(0, 50)));
  renderBookmarks();
}
function isBookmarked(tag) {
  return getBookmarks().some(b => b.tag === tag);
}
function addOrUpdateBookmark(tag, name, trophies) {
  const bms = getBookmarks().filter(b => b.tag !== tag);
  bms.unshift({ tag, name: name || "", trophies: trophies || 0 });
  setBookmarksAndRender(bms);
}
function removeBookmark(tag) {
  setBookmarksAndRender(getBookmarks().filter(b => b.tag !== tag));
}

function toggleCurrentBookmark() {
  const tag = MYPAGE_DATA?.tag || normalizeTag(document.getElementById("mypage-tag").value);
  if (!tag || tag.length < 4) return;
  if (isBookmarked(tag)) {
    removeBookmark(tag);
  } else {
    const profile = MYPAGE_DATA?.profile || {};
    addOrUpdateBookmark(tag, profile.name, profile.trophies);
  }
  updateBookmarkButtonState();
}

function updateBookmarkButtonState() {
  const btn = document.getElementById("mypage-bookmark");
  if (!btn) return;
  const tag = MYPAGE_DATA?.tag || normalizeTag(document.getElementById("mypage-tag").value);
  const marked = tag && isBookmarked(tag);
  btn.textContent = marked ? "★" : "☆";
  btn.classList.toggle("bg-yellow-600", marked);
  btn.classList.toggle("bg-gray-700", !marked);
  btn.title = marked ? "ブックマーク解除" : "ブックマーク追加";
}

function renderBookmarks() {
  const el = document.getElementById("mypage-bookmarks");
  if (!el) return;
  const bms = getBookmarks();
  if (bms.length === 0) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = `
    <div class="bg-gray-800 p-3 rounded">
      <div class="text-xs text-gray-400 mb-2">ブックマーク (${bms.length}/50)</div>
      <div class="flex flex-wrap gap-2">
        ${bms.map((b, i) => `
          <div class="flex items-center bg-gray-700 hover:bg-gray-600 rounded overflow-hidden text-sm">
            <button onclick="openBookmark(${i})" class="px-3 py-1.5 flex items-center gap-1.5">
              <span class="font-semibold truncate max-w-[120px]">${escapeHtml(b.name || b.tag)}</span>
              ${b.trophies ? `<span class="text-xs text-yellow-400">🏆${b.trophies.toLocaleString()}</span>` : ""}
            </button>
            <button onclick="removeBookmarkAt(${i})" class="px-2 py-1.5 text-gray-400 hover:text-red-400 hover:bg-gray-800" title="削除">×</button>
          </div>
        `).join("")}
      </div>
    </div>`;
  updateBookmarkButtonState();
}

function openBookmark(idx) {
  const b = getBookmarks()[idx];
  if (!b) return;
  document.getElementById("mypage-tag").value = b.tag;
  fetchMypage(b.tag);
}

function removeBookmarkAt(idx) {
  const b = getBookmarks()[idx];
  if (b) removeBookmark(b.tag);
}

// 共通: 検索ボックスに名前サジェストを取り付ける
function attachNameSuggest(input, suggestEl, kind, onSelect) {
  let timer = null;
  let lastQuery = "";
  input.addEventListener("input", () => {
    const v = input.value.trim();
    // タグ (# で始まる) はサジェスト対象外
    if (!v || v.startsWith("#") || v.length < 1) {
      hideSuggest(suggestEl);
      return;
    }
    if (v === lastQuery) return;
    lastQuery = v;
    if (timer) clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const url = `${API_HOST}/api/search/${kind}?q=${encodeURIComponent(v)}&limit=20`;
        const res = await fetch(url);
        if (!res.ok) { hideSuggest(suggestEl); return; }
        const data = await res.json();
        renderSuggest(suggestEl, data.results || [], onSelect);
      } catch (e) { hideSuggest(suggestEl); }
    }, 250);
  });
  // クリック外で閉じる
  document.addEventListener("click", e => {
    if (!suggestEl.contains(e.target) && e.target !== input) hideSuggest(suggestEl);
  });
}

function hideSuggest(el) { if (el) el.classList.add("hidden"); }

function renderSuggest(el, results, onSelect) {
  if (!el) return;
  if (results.length === 0) {
    el.innerHTML = '<div class="px-3 py-2 text-sm text-gray-500">該当なし</div>';
    el.classList.remove("hidden");
    return;
  }
  el.innerHTML = results.map((r, i) => `
    <div data-idx="${i}" class="px-3 py-2 text-sm cursor-pointer hover:bg-gray-700 flex items-center justify-between border-b border-gray-700/50 last:border-0">
      <span class="truncate flex-1">${escapeHtml(r.name)}</span>
      <span class="ml-2 text-xs text-gray-400 font-mono">${escapeHtml(r.tag)}</span>
      <span class="ml-2 text-xs text-yellow-400">🏆${r.trophies.toLocaleString()}</span>
    </div>`).join("");
  el.classList.remove("hidden");
  el.querySelectorAll("[data-idx]").forEach(node => {
    node.addEventListener("click", () => {
      const idx = parseInt(node.dataset.idx, 10);
      onSelect(results[idx]);
    });
  });
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
    const f = MYPAGE_BATTLES_FILTER;
    const filterQs = [
      f.brawler ? `&brawler=${encodeURIComponent(f.brawler)}` : "",
      f.map ? `&map=${encodeURIComponent(f.map)}` : "",
      f.rank ? `&rank=${encodeURIComponent(f.rank)}` : "",
    ].join("");
    const battlesUrl = `${API_HOST}/api/player/${encTag}/battles?limit=${MYPAGE_BATTLES_PER_PAGE}&offset=${offset}${filterQs}`;
    const statsUrl = `${API_HOST}/api/player/${encTag}?period=${encodeURIComponent(MYPAGE_PERIOD)}`;
    const recentUrl = `${API_HOST}/api/player/${encTag}?period=7d`;
    const requests = options.pageOnly
      ? [Promise.resolve(null), fetch(battlesUrl), Promise.resolve(null)]
      : [fetch(statsUrl), fetch(battlesUrl), fetch(recentUrl)];
    const [statsRes, battlesRes, recentRes] = await Promise.all(requests);
    if (!options.pageOnly) {
      if (!statsRes.ok) {
        const body = await statsRes.json().catch(() => ({ detail: statsRes.statusText }));
        throw new Error(body.detail || `HTTP ${statsRes.status}`);
      }
      MYPAGE_DATA = await statsRes.json();
      MYPAGE_RECENT_STATS = recentRes && recentRes.ok ? (await recentRes.json()).stats?.summary : null;
    }
    if (battlesRes && battlesRes.ok) {
      const bj = await battlesRes.json();
      MYPAGE_DATA.battles = bj.battles || [];
      MYPAGE_BATTLES_TOTAL = bj.total || 0;
    } else {
      MYPAGE_DATA.battles = [];
      MYPAGE_BATTLES_TOTAL = 0;
    }
    // matchupsはセクション開いた時に遅延fetch
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

  // クールダウンUI + ブックマークボタン状態
  document.getElementById("mypage-refresh").classList.remove("hidden");
  startCooldownTimer(d.cooldown_seconds || 0);
  updateBookmarkButtonState();
  // 既にブックマーク済みなら最新の name/trophies で更新
  if (d.tag && isBookmarked(d.tag)) {
    const p = d.profile || {};
    addOrUpdateBookmark(d.tag, p.name, p.trophies);
  }

  el.innerHTML = `
    ${renderMypageHeader(d, profile, period)}
    ${total === 0 ? renderEmptyState() : `
      ${renderMypageSummary(total, top2, top2Rate, rank1, rank1Rate, avgRank)}
      ${renderMypageSectionSelector()}
      ${MYPAGE_SECTION === "history" ? `
        ${renderMypageBattleFilters(stats.brawlers || [], stats.maps || [], brawlerJp, mapJp)}
        ${renderMypageHeatmap(d.battles || [], brawlerImg)}
        ${renderMypageBattleList(d.battles || [], brawlerImg, brawlerJp, mapJp)}
      ` : ""}
      ${MYPAGE_SECTION === "matchups" ? renderMypageMatchups(brawlerJp, brawlerImg) : ""}
      ${MYPAGE_SECTION === "brawlers" ? renderMypageBrawlers(stats.brawlers || [], brawlerJp, brawlerImg, globalBrawlerStats, total) : ""}
      ${MYPAGE_SECTION === "maps" ? renderMypageMaps(stats.maps || [], mapJp) : ""}
      ${MYPAGE_SECTION === "recommend" ? renderMypageRecommendations(stats.brawlers || [], brawlerJp, brawlerImg, globalBrawlerStats) : ""}
      ${MYPAGE_SECTION === "collection" ? renderMypageCollection(profile, brawlerJp, brawlerImg) : ""}
      ${MYPAGE_SECTION === "botobs" ? renderMypageBotObs(MYPAGE_DATA.tag, profile) : ""}
    `}
    <div class="text-xs text-gray-500 mt-4 text-center">
      ウォッチリスト ${d.watchlist_count}/${d.watchlist_max} ・
      ${d.last_fetched_at ? `最終取得: ${new Date(d.last_fetched_at * 1000).toLocaleString("ja-JP")}` : "未取得"}
    </div>`;
}

function renderMypageHeader(d, profile, period) {
  const regAt = profile.registered_at
    ? new Date(profile.registered_at * 1000).toLocaleDateString(LANG === "en" ? "en-US" : "ja-JP")
    : "—";
  const periods = [
    { val: "1d", label: t("period_1d") },
    { val: "7d", label: t("period_7d") },
    { val: "30d", label: t("period_30d") },
    { val: "all", label: t("period_all") },
  ];
  const periodBtns = periods.map(p => {
    const active = MYPAGE_PERIOD === p.val;
    return `<button onclick="changeMypagePeriod('${p.val}')" class="px-3 py-1 rounded text-xs font-bold ${active ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}">${p.label}</button>`;
  }).join("");
  // 公式API由来の追加プロフィール
  const iconId = profile.icon;
  const iconUrl = iconId ? `https://cdn.brawlify.com/profile-icons/regular/${iconId}.png` : null;
  const nameColor = profile.nameColor ? "#" + (profile.nameColor.toString(16) || "").slice(-6) : null;
  const club = profile.club || {};
  const stats = [
    profile.expLevel ? `<span class="text-purple-300">Lv.${profile.expLevel}</span>` : "",
    profile.totalPrestigeLevel ? `<span class="text-fuchsia-300">プレ${profile.totalPrestigeLevel}</span>` : "",
    profile.victories_3v3 ? `<span class="text-cyan-300">3v3勝利 ${profile.victories_3v3.toLocaleString()}</span>` : "",
    profile.victories_solo ? `<span class="text-amber-300">ソロ勝利 ${profile.victories_solo.toLocaleString()}</span>` : "",
    profile.victories_duo ? `<span class="text-pink-300">デュオ勝利 ${profile.victories_duo.toLocaleString()}</span>` : "",
  ].filter(Boolean).join('<span class="text-gray-600 mx-1">·</span>');
  // ガチバトル段位
  let rankedHtml = "";
  if (profile.rankedRankName || profile.rankedElo) {
    const cur = profile.rankedRankName ? `${profile.rankedRankName}` : "";
    const elo = profile.rankedElo ? ` (Elo ${profile.rankedElo.toLocaleString()})` : "";
    const best = profile.highestAllTimeRankedRankName && profile.highestAllTimeRankedElo
      ? ` <span class="text-gray-500">最高 ${profile.highestAllTimeRankedRankName} (Elo ${profile.highestAllTimeRankedElo.toLocaleString()})</span>`
      : "";
    rankedHtml = `<div class="text-xs mt-1 flex items-center gap-1 flex-wrap">
      <span class="text-red-400 font-bold">🏆 ガチ ${escapeHtml(cur)}${escapeHtml(elo)}</span>
      ${best}
    </div>`;
  }
  return `
    <div class="bg-gray-800 p-4 rounded mb-4">
      <div class="flex items-start gap-3">
        ${iconUrl ? `<img src="${iconUrl}" class="w-16 h-16 rounded shrink-0" onerror="this.style.display='none'">` : ""}
        <div class="flex-1 min-w-0">
          <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 class="text-xl font-bold" ${nameColor ? `style="color:${nameColor}"` : ""}>${escapeHtml(profile.name || d.tag)}</h2>
            <span class="text-sm text-gray-400 font-mono">${escapeHtml(d.tag)}</span>
            ${profile.trophies ? `<span class="text-sm text-yellow-400">🏆 ${profile.trophies.toLocaleString()}</span>` : ""}
            ${profile.highest_trophies ? `<span class="text-sm text-orange-400">最高 ${profile.highest_trophies.toLocaleString()}</span>` : ""}
          </div>
          ${stats ? `<div class="text-xs mt-1.5 flex flex-wrap gap-x-1">${stats}</div>` : ""}
          ${rankedHtml}
          ${club.tag ? `<div class="text-xs text-gray-400 mt-1">🛡️ <button onclick="openClubFromMypage('${escapeHtml(club.tag)}')" class="text-blue-300 hover:underline">${escapeHtml(club.name || club.tag)}</button></div>` : ""}
          <div class="text-xs text-gray-500 mt-1">登録: ${regAt} ・ ${t("period_label")}: ${period}</div>
        </div>
      </div>
      <div class="flex flex-wrap gap-1 mt-3">
        <span class="text-xs text-gray-400 mr-1 self-center">${t("period_label")}:</span>
        ${periodBtns}
      </div>
    </div>`;
}

function openClubFromMypage(tag) {
  document.getElementById("club-tag").value = tag;
  document.querySelector('.tab-btn[data-tab="club"]').click();
  fetchClub(tag);
}

function changeMypagePeriod(p) {
  if (MYPAGE_PERIOD === p) return;
  MYPAGE_PERIOD = p;
  localStorage.setItem("mypage_period", p);
  if (MYPAGE_DATA && MYPAGE_DATA.tag) {
    fetchMypage(MYPAGE_DATA.tag);
  }
}

function renderMypageSectionSelector() {
  const sections = [
    { val: "history", label: t("section_history") },
    { val: "matchups", label: t("section_matchups") },
    { val: "brawlers", label: t("section_brawlers") },
    { val: "maps", label: t("section_maps") },
    { val: "recommend", label: t("section_recommend") },
    { val: "collection", label: LANG === "en" ? "Collection" : "コレクション" },
    { val: "botobs", label: LANG === "en" ? "Practice bot card" : "練習試合 botカード" },
  ];
  return `
    <div class="mb-3">
      <select onchange="setMypageSection(this.value)" class="w-full sm:w-auto p-2 bg-gray-900 border border-gray-700 rounded text-base">
        ${sections.map(s => `<option value="${s.val}" ${MYPAGE_SECTION === s.val ? "selected" : ""}>${escapeHtml(s.label)}</option>`).join("")}
      </select>
    </div>`;
}

function setMypageSection(s) {
  MYPAGE_SECTION = s;
  localStorage.setItem("mypage_section", s);
  renderMypage();
}

function renderEmptyState() {
  return `
    <div class="bg-yellow-900/30 border border-yellow-700 p-4 rounded text-yellow-200">
      まだトリオサバイバルの試合データがありません。<br>
      <span class="text-sm text-yellow-300">プレイ後、30分ごとに自動取得されます。「更新」ボタンで即時取得もできます。</span>
    </div>`;
}

function renderMypageSummary(total, top2, top2Rate, rank1, rank1Rate, avgRank) {
  // 直近7日との比較 (MYPAGE_RECENT_STATS)
  const r = MYPAGE_RECENT_STATS;
  const cmp = (cur, prev, fmt, color) => {
    if (!r || prev == null || prev === undefined) return "";
    const diff = cur - prev;
    if (Math.abs(diff) < 0.01) return `<span class="text-[10px] text-gray-500"> ±0</span>`;
    const sign = diff > 0 ? "▲+" : "▼";
    const cl = (color === "rev" ? (diff < 0 ? "text-green-400" : "text-red-400") : (diff > 0 ? "text-green-400" : "text-red-400"));
    return `<span class="text-[10px] ${cl} ml-1">${sign}${fmt(Math.abs(diff))}</span>`;
  };
  const r7_total = r?.total || 0;
  const r7_rank1Rate = r && r.total ? (r.rank1 / r.total * 100) : null;
  const r7_top2Rate = r && r.total ? (r.top2 / r.total * 100) : null;
  const r7_avgRank = r?.avg_rank || null;
  const pctFmt = v => v.toFixed(1) + "%";
  const numFmt = v => v.toFixed(2);
  return `
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
      <div class="bg-gray-800 p-3 rounded text-center">
        <div class="text-2xl font-bold">${total.toLocaleString()}</div>
        <div class="text-xs text-gray-400">${t("summary_total")}</div>
        ${r ? `<div class="text-[10px] text-gray-500 mt-1">7d: ${r7_total.toLocaleString()}</div>` : ""}
      </div>
      <div class="bg-gray-800 p-3 rounded text-center">
        <div class="text-2xl font-bold text-green-400">${rank1Rate.toFixed(1)}%</div>
        <div class="text-xs text-gray-400">${t("summary_rank1")} (${rank1})</div>
        ${r7_rank1Rate != null ? `<div class="text-[10px] text-gray-500 mt-1">7d: ${r7_rank1Rate.toFixed(1)}%${cmp(rank1Rate, r7_rank1Rate, pctFmt)}</div>` : ""}
      </div>
      <div class="bg-gray-800 p-3 rounded text-center">
        <div class="text-2xl font-bold text-blue-400">${top2Rate.toFixed(1)}%</div>
        <div class="text-xs text-gray-400">${t("summary_top2")} (${top2})</div>
        ${r7_top2Rate != null ? `<div class="text-[10px] text-gray-500 mt-1">7d: ${r7_top2Rate.toFixed(1)}%${cmp(top2Rate, r7_top2Rate, pctFmt)}</div>` : ""}
      </div>
      <div class="bg-gray-800 p-3 rounded text-center">
        <div class="text-2xl font-bold">${avgRank.toFixed(2)}</div>
        <div class="text-xs text-gray-400">${t("summary_avg")}</div>
        ${r7_avgRank != null ? `<div class="text-[10px] text-gray-500 mt-1">7d: ${r7_avgRank.toFixed(2)}${cmp(avgRank, r7_avgRank, numFmt, "rev")}</div>` : ""}
      </div>
    </div>`;
}

// 試合履歴フィルタUI
function renderMypageBattleFilters(brawlers, maps, brawlerJp, mapJp) {
  const f = MYPAGE_BATTLES_FILTER;
  const brOpts = ['<option value="">' + t("filter_all") + '</option>'].concat(
    brawlers.map(b => `<option value="${escapeHtml(b.brawler)}" ${f.brawler === b.brawler ? "selected" : ""}>${escapeHtml(brawlerJp[b.brawler] || b.brawler)} (${b.picks})</option>`)
  ).join("");
  const mpOpts = ['<option value="">' + t("filter_all") + '</option>'].concat(
    maps.map(m => `<option value="${escapeHtml(m.map)}" ${f.map === m.map ? "selected" : ""}>${escapeHtml(mapJp[m.map] || m.map)} (${m.picks})</option>`)
  ).join("");
  const rkOpts = [
    `<option value="">${t("filter_all")}</option>`,
    `<option value="1" ${f.rank==="1"?"selected":""}>1</option>`,
    `<option value="2" ${f.rank==="2"?"selected":""}>2</option>`,
    `<option value="3" ${f.rank==="3"?"selected":""}>3</option>`,
    `<option value="4" ${f.rank==="4"?"selected":""}>4</option>`,
  ].join("");
  const hasFilter = f.brawler || f.map || f.rank;
  return `
    <div class="bg-gray-800 p-3 rounded mb-3 flex flex-wrap gap-2 items-center">
      <span class="text-xs text-gray-400 mr-1">フィルタ:</span>
      <select onchange="setBattlesFilter('brawler', this.value)" class="p-1.5 bg-gray-900 border border-gray-700 rounded text-sm">${brOpts}</select>
      <select onchange="setBattlesFilter('map', this.value)" class="p-1.5 bg-gray-900 border border-gray-700 rounded text-sm">${mpOpts}</select>
      <select onchange="setBattlesFilter('rank', this.value)" class="p-1.5 bg-gray-900 border border-gray-700 rounded text-sm">${rkOpts}</select>
      ${hasFilter ? `<button onclick="resetBattlesFilter()" class="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs">${t("filter_reset")}</button>` : ""}
    </div>`;
}

function setBattlesFilter(key, val) {
  MYPAGE_BATTLES_FILTER[key] = val || "";
  MYPAGE_BATTLES_PAGE = 1;
  if (MYPAGE_DATA && MYPAGE_DATA.tag) fetchMypage(MYPAGE_DATA.tag, { pageOnly: true });
}

function resetBattlesFilter() {
  MYPAGE_BATTLES_FILTER = { brawler: "", map: "", rank: "" };
  MYPAGE_BATTLES_PAGE = 1;
  if (MYPAGE_DATA && MYPAGE_DATA.tag) fetchMypage(MYPAGE_DATA.tag, { pageOnly: true });
}

// マッチアップ分析 (遅延 fetch)
async function fetchMatchupsIfNeeded() {
  if (!MYPAGE_DATA || !MYPAGE_DATA.tag) return;
  if (MYPAGE_MATCHUPS && MYPAGE_MATCHUPS._tag === MYPAGE_DATA.tag && MYPAGE_MATCHUPS._period === MYPAGE_PERIOD) return;
  const tag = MYPAGE_DATA.tag;
  const period = MYPAGE_PERIOD;
  try {
    const res = await fetch(`${API_HOST}/api/player/${encodeURIComponent(tag)}/matchups?period=${period}&min_seen=5`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const j = await res.json();
    j._tag = tag; j._period = period;
    MYPAGE_MATCHUPS = j;
    renderMypage();
  } catch (e) {
    document.getElementById("mypage-detail").querySelector("#matchup-area")?.replaceChildren();
  }
}

function renderMypageMatchups(brawlerJp, brawlerImg) {
  const m = MYPAGE_MATCHUPS;
  if (!m || m._tag !== MYPAGE_DATA?.tag || m._period !== MYPAGE_PERIOD) {
    setTimeout(fetchMatchupsIfNeeded, 50);
    return `<div id="matchup-area" class="bg-gray-800 p-6 rounded text-center text-gray-400">${t("loading")}</div>`;
  }
  if ((!m.global || m.global.length === 0) && (!m.by_my_brawler || m.by_my_brawler.length === 0)) {
    return `<div class="bg-yellow-900/30 border border-yellow-700 p-4 rounded text-yellow-200">${t("no_data")} (5戦以上必要)</div>`;
  }
  // 全体: avg_rank 高い (苦手) TOP10
  const globalTough = (m.global || []).slice(0, 10);
  // 自分のブロウラーごとの相性 (avg_rank 高い = 苦手) TOP15
  const byMyTough = [...(m.by_my_brawler || [])].sort((a,b)=>-a.avg_rank + b.avg_rank).reverse().slice(0, 15);
  // wait, sort by avg_rank DESC
  const byMyToughSorted = [...(m.by_my_brawler || [])].sort((a,b)=>b.avg_rank - a.avg_rank).slice(0, 15);

  const renderEnemyRow = (r, idx, showMy = false) => {
    const ebJp = brawlerJp[r.enemy_brawler] || r.enemy_brawler;
    const myJp = showMy ? (brawlerJp[r.my_brawler] || r.my_brawler) : "";
    const eImg = brawlerImg[r.enemy_brawler];
    const mImg = showMy ? brawlerImg[r.my_brawler] : "";
    const wrColor = r.avg_rank >= 3 ? "text-red-300" : r.avg_rank >= 2.5 ? "text-yellow-300" : "text-green-300";
    return `<tr class="border-b border-gray-700/50 hover:bg-gray-700/30">
      <td class="py-2 px-2 text-gray-500 text-xs w-8">${idx + 1}</td>
      ${showMy ? `<td class="py-2 px-2"><div class="flex items-center gap-1">${mImg?`<img src="${mImg}" class="w-6 h-6 rounded">`:''}<span class="text-sm truncate max-w-[80px]">${escapeHtml(myJp)}</span></div></td>` : ""}
      <td class="py-2 px-2"><div class="flex items-center gap-1">${eImg?`<img src="${eImg}" class="w-6 h-6 rounded">`:''}<span class="text-sm truncate max-w-[80px]">${escapeHtml(ebJp)}</span></div></td>
      <td class="py-2 px-2 text-right font-mono text-xs">${r.seen}</td>
      <td class="py-2 px-2 text-right font-mono ${wrColor} text-xs">${r.avg_rank.toFixed(2)}</td>
      <td class="py-2 px-2 text-right font-mono text-blue-300 text-xs">${(r.top2_rate*100).toFixed(0)}%</td>
    </tr>`;
  };

  return `
    <div id="matchup-area" class="bg-gray-800 p-4 rounded mb-4">
      <h3 class="text-sm font-bold mb-2 text-gray-300 uppercase tracking-wide">${t("matchup_global")}</h3>
      <div class="overflow-x-auto -mx-2">
      <table class="w-full text-sm">
        <thead><tr class="text-left text-xs text-gray-400 border-b border-gray-700">
          <th class="pb-2 px-2">#</th>
          <th class="pb-2 px-2">${t("matchup_enemy")}</th>
          <th class="pb-2 px-2 text-right">${t("matchup_seen")}</th>
          <th class="pb-2 px-2 text-right">${t("matchup_avg_rank")}</th>
          <th class="pb-2 px-2 text-right">${t("summary_top2")}</th>
        </tr></thead>
        <tbody>${globalTough.map((r,i)=>renderEnemyRow(r,i,false)).join("")}</tbody>
      </table>
      </div>
      <h3 class="text-sm font-bold mt-6 mb-2 text-gray-300 uppercase tracking-wide">自分のブロウラー × 敵 (苦手TOP15)</h3>
      <div class="overflow-x-auto -mx-2">
      <table class="w-full text-sm">
        <thead><tr class="text-left text-xs text-gray-400 border-b border-gray-700">
          <th class="pb-2 px-2">#</th>
          <th class="pb-2 px-2">${t("matchup_my")}</th>
          <th class="pb-2 px-2">${t("matchup_enemy")}</th>
          <th class="pb-2 px-2 text-right">${t("matchup_seen")}</th>
          <th class="pb-2 px-2 text-right">${t("matchup_avg_rank")}</th>
          <th class="pb-2 px-2 text-right">${t("summary_top2")}</th>
        </tr></thead>
        <tbody>${byMyToughSorted.map((r,i)=>renderEnemyRow(r,i,true)).join("")}</tbody>
      </table>
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
      const clickable = m.tag ? `onclick="event.stopPropagation(); openMypage('${escapeHtml(m.tag)}')"` : '';
      return `<div ${clickable} class="flex items-center gap-1 px-1 py-0.5 rounded ${isMe ? 'bg-yellow-700/30 ring-1 ring-yellow-500' : 'bg-gray-700/40 hover:bg-blue-700/40'} ${m.tag ? 'cursor-pointer' : ''}" title="${m.tag ? 'クリックでマイページへ' : ''}">
        ${img ? `<img src="${img}" class="w-6 h-6 rounded" loading="lazy">` : ""}
        <div class="text-xs leading-tight">
          <div class="truncate max-w-[70px]">${escapeHtml(m.name || m.brawler)}</div>
          <div class="text-[10px] text-gray-400">🏆${m.trophies}</div>
        </div>
      </div>`;
    }).join("")}
  </div>`;
}

// 汎用: 任意のタグでマイページに移動
function openMypage(tag) {
  if (!tag) return;
  document.getElementById("mypage-tag").value = tag;
  document.querySelector('.tab-btn[data-tab="mypage"]').click();
  fetchMypage(tag);
  window.scrollTo({ top: 0, behavior: "smooth" });
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

// ブロウラーコレクション (公式APIから取得した所持データ)
function renderMypageCollection(profile, brawlerJp, brawlerImg) {
  const owned = profile.brawlers || [];
  if (owned.length === 0) {
    return `<div class="bg-gray-800 p-6 rounded text-center text-gray-400">${t("no_data")}</div>`;
  }
  // 全ブロウラー (102体) を所持/未所持で分類 (DB.brawlers を参照)
  const ownedByName = {};
  for (const b of owned) ownedByName[b.name] = b;
  const allBrawlers = (DB?.brawlers || []).slice();

  // 統計: 所持率、 マスタリー
  const totalBr = allBrawlers.length || owned.length;
  const ownedCount = owned.length;
  const ownedRate = totalBr ? (ownedCount / totalBr * 100) : 0;
  const totalGears = owned.reduce((s, b) => s + (b.gears || 0), 0);
  const totalSP = owned.reduce((s, b) => s + (b.starPowers || 0), 0);
  const totalGad = owned.reduce((s, b) => s + (b.gadgets || 0), 0);
  const totalHC = owned.reduce((s, b) => s + (b.hyperCharge || 0), 0);

  // 並び: ランク降順 → 各ブロウラートロフィー降順
  owned.sort((a, b) => (b.rank || 0) - (a.rank || 0) || (b.trophies || 0) - (a.trophies || 0));

  // 未所持ブロウラー
  const ownedSet = new Set(owned.map(b => b.name));
  const unowned = allBrawlers.filter(b => !ownedSet.has(b.name));

  const renderCard = (b) => {
    const img = brawlerImg[b.name];
    const jp = brawlerJp[b.name] || b.name;
    const rk = b.rank || 0;
    const rkColor = rk >= 35 ? "text-yellow-300" : rk >= 25 ? "text-orange-300" : rk >= 15 ? "text-blue-300" : "text-gray-400";
    return `<div class="relative p-1 bg-gray-700/30 rounded text-center">
      ${b.hyperCharge ? `<span class="absolute top-0 right-0 text-[10px] bg-purple-600 text-white rounded-bl px-0.5">HC</span>` : ""}
      ${img ? `<img src="${img}" class="w-full rounded">` : '<div class="w-full aspect-square bg-gray-700 rounded"></div>'}
      <div class="text-[10px] mt-0.5 truncate font-semibold">${escapeHtml(jp)}</div>
      <div class="text-[10px] ${rkColor}">R${rk} <span class="text-yellow-400">🏆${b.trophies||0}</span></div>
      <div class="text-[9px] text-gray-400">P${b.power||0} <span class="text-gray-500">${b.starPowers||0}sp ${b.gadgets||0}g</span></div>
    </div>`;
  };

  const renderUnownedCard = (b) => {
    const img = brawlerImg[b.name];
    const jp = brawlerJp[b.name] || b.name;
    return `<div class="p-1 bg-gray-800 rounded text-center opacity-40">
      ${img ? `<img src="${img}" class="w-full rounded grayscale">` : '<div class="w-full aspect-square bg-gray-700 rounded"></div>'}
      <div class="text-[10px] mt-0.5 truncate text-gray-500">${escapeHtml(jp)}</div>
    </div>`;
  };

  const gridCls = "grid grid-cols-5 sm:grid-cols-8 md:grid-cols-10 lg:grid-cols-12 xl:grid-cols-15 gap-1";
  return `
    <div class="bg-gray-800 p-4 rounded mb-4">
      <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-3">
        <h3 class="text-sm font-bold text-gray-300 uppercase tracking-wide">${LANG === "en" ? "Collection" : "コレクション"}</h3>
        <span class="text-sm text-gray-400">${ownedCount}/${totalBr} (${ownedRate.toFixed(1)}%)</span>
      </div>
      <div class="flex flex-wrap gap-3 text-xs mb-3">
        <span class="text-yellow-300">🎁 ${totalGears} ${LANG === "en" ? "gears" : "ギア"}</span>
        <span class="text-orange-300">⭐ ${totalSP} ${LANG === "en" ? "star powers" : "スタパ"}</span>
        <span class="text-cyan-300">⚙️ ${totalGad} ${LANG === "en" ? "gadgets" : "ガジェット"}</span>
        <span class="text-purple-300">🔋 ${totalHC} ${LANG === "en" ? "hyper charges" : "ハイチャ"}</span>
      </div>
      <div class="${gridCls}">${owned.map(renderCard).join("")}</div>
      ${unowned.length > 0 ? `
        <details class="mt-4">
          <summary class="cursor-pointer text-xs text-gray-400 hover:text-gray-200">${LANG === "en" ? "Unowned" : "未所持"} ${unowned.length}${LANG === "en" ? "" : "体"}</summary>
          <div class="${gridCls} mt-2">${unowned.map(renderUnownedCard).join("")}</div>
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
setupClub();
setupRoulette();
setupRanking();
setupQueue();

// ============================================================
// ランキング (全ウォッチリストプレイヤーの戦績)
// ============================================================

function setupRanking() {
  const orderSel = document.getElementById("ranking-order");
  const minSel = document.getElementById("ranking-min");
  const periodSel = document.getElementById("ranking-period");
  const refresh = document.getElementById("ranking-refresh");
  if (!orderSel || !refresh) return;
  const fetchAndRender = () => fetchRanking();
  refresh.addEventListener("click", fetchAndRender);
  orderSel.addEventListener("change", fetchAndRender);
  minSel.addEventListener("change", fetchAndRender);
  periodSel.addEventListener("change", fetchAndRender);
  // タブ切替時に初回ロード
  const tabBtn = document.querySelector('.tab-btn[data-tab="ranking"]');
  if (tabBtn) {
    tabBtn.addEventListener("click", () => {
      const result = document.getElementById("ranking-result");
      if (result && !result.dataset.loaded) fetchAndRender();
    });
  }
}

async function fetchRanking() {
  const result = document.getElementById("ranking-result");
  if (!result) return;
  const order = document.getElementById("ranking-order").value;
  const minBattles = document.getElementById("ranking-min").value;
  const period = document.getElementById("ranking-period").value;
  result.innerHTML = '<div class="bg-gray-800 p-6 rounded text-center text-gray-400">読込中...</div>';
  try {
    const url = `${API_HOST}/api/leaderboard?order=${order}&min_battles=${minBattles}&period=${period}&limit=200`;
    const res = await fetch(url);
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderRanking(data, order);
    result.dataset.loaded = "1";
  } catch (e) {
    result.innerHTML = `<div class="bg-red-900/30 border border-red-700 p-4 rounded text-red-200">取得失敗: ${escapeHtml(e.message)}</div>`;
  }
}

function renderRanking(data, order) {
  const result = document.getElementById("ranking-result");
  const rows = data.results || [];
  if (rows.length === 0) {
    result.innerHTML = '<div class="bg-yellow-900/30 border border-yellow-700 p-4 rounded text-yellow-200">条件に該当するプレイヤーがいません。 最低試合数を下げるか、 もっと多くのプレイヤーを「マイページ」 で検索してください。</div>';
    return;
  }
  const renderRow = (r, i) => {
    const rank1pct = (r.rank1_rate * 100).toFixed(1);
    const top2pct = (r.top2_rate * 100).toFixed(1);
    const rank4pct = ((r.rank4_rate || 0) * 100).toFixed(1);
    const avg = r.avg_rank.toFixed(2);
    return `<tr class="border-b border-gray-700/50 hover:bg-gray-700/30 cursor-pointer" onclick="openMypage('${escapeHtml(r.tag)}')">
      <td class="py-2 px-2 text-gray-500 text-xs w-10">${i + 1}</td>
      <td class="py-2 px-2 truncate max-w-[150px]" title="${escapeHtml(r.name || r.tag)}">${escapeHtml(r.name || r.tag)}</td>
      <td class="py-2 px-2 text-xs text-gray-400 font-mono hidden sm:table-cell">${escapeHtml(r.tag)}</td>
      <td class="py-2 px-2 text-right text-yellow-400 font-mono text-xs hidden md:table-cell">🏆${(r.trophies || 0).toLocaleString()}</td>
      <td class="py-2 px-2 text-right font-mono text-xs">${r.battles.toLocaleString()}</td>
      <td class="py-2 px-2 text-right font-mono ${order === "rank1_rate" ? "text-green-300 font-bold" : "text-green-300"} text-xs">${rank1pct}%</td>
      <td class="py-2 px-2 text-right font-mono ${order === "top2_rate" ? "text-blue-300 font-bold" : "text-blue-300"} text-xs hidden sm:table-cell">${top2pct}%</td>
      <td class="py-2 px-2 text-right font-mono ${order === "rank4_rate_low" ? "text-red-300 font-bold" : "text-red-300"} text-xs hidden md:table-cell">${rank4pct}%</td>
      <td class="py-2 px-2 text-right font-mono ${order === "avg_rank" ? "font-bold" : ""} text-xs">${avg}</td>
    </tr>`;
  };
  result.innerHTML = `
    <div class="bg-gray-800 p-4 rounded">
      <div class="text-xs text-gray-400 mb-2">${rows.length}人 (${data.params.min_battles}戦以上 / ${data.params.period === "all" ? "全期間" : "直近" + data.params.period.replace("d", "日")})</div>
      <div class="overflow-x-auto -mx-2">
      <table class="w-full text-sm">
        <thead><tr class="text-left text-xs text-gray-400 border-b border-gray-700">
          <th class="pb-2 px-2">#</th>
          <th class="pb-2 px-2">名前</th>
          <th class="pb-2 px-2 hidden sm:table-cell">タグ</th>
          <th class="pb-2 px-2 text-right hidden md:table-cell">トロ</th>
          <th class="pb-2 px-2 text-right">試合</th>
          <th class="pb-2 px-2 text-right">1位率</th>
          <th class="pb-2 px-2 text-right hidden sm:table-cell">TOP2率</th>
          <th class="pb-2 px-2 text-right hidden md:table-cell">4位率</th>
          <th class="pb-2 px-2 text-right">平均順</th>
        </tr></thead>
        <tbody>${rows.map(renderRow).join("")}</tbody>
      </table>
      </div>
    </div>`;
}

// ============================================================
// ルーレット (ランダム編成)
// ============================================================

function setupRoulette() {
  const mapSel = document.getElementById("roulette-map");
  const tierSel = document.getElementById("roulette-tier");
  const spinBtn = document.getElementById("roulette-spin");
  if (!mapSel || !spinBtn) return;
  // タブ切替時にマップを最新化
  const tabBtn = document.querySelector('.tab-btn[data-tab="roulette"]');
  if (tabBtn) tabBtn.addEventListener("click", () => setTimeout(populateRouletteMaps, 50));
  spinBtn.addEventListener("click", () => spinRoulette());
}

function populateRouletteMaps() {
  const sel = document.getElementById("roulette-map");
  if (!sel || !DB) return;
  if (sel.options.length > 0) return;  // 既に投入済
  const opts = ['<option value="">マップ指定なし</option>'];
  if (ROTATION) {
    const todayJp = rotationMapForDate(new Date());
    const dbByJp = new Map();
    for (const m of DB.maps) dbByJp.set(m.name_jp || m.name, m);
    for (const jp of ROTATION.rotation) {
      const m = dbByJp.get(jp);
      if (!m) continue;
      const isToday = jp === todayJp;
      opts.push(`<option value="${escapeHtml(m.hash)}" ${isToday ? "selected" : ""}>${escapeHtml(jp)}${isToday ? " 【今日】" : ""}</option>`);
    }
  }
  sel.innerHTML = opts.join("");
}

function _rouletteCandidates() {
  // 対象ブロウラーリストを返す: [{name, name_jp, image_url, tier?, win_rate?}]
  if (!DB || !DB.brawlers) return [];
  const tierFilter = document.getElementById("roulette-tier")?.value || "all";
  const mapHash = document.getElementById("roulette-map")?.value || "";
  const mapObj = mapHash ? DB.maps.find(m => m.hash === mapHash) : null;

  const TIER_RANK = { "S+": 5, "S": 4, "A": 3, "B": 2, "C": 1, "?": 0 };
  let pool = DB.brawlers.map(b => ({
    name: b.name,
    name_jp: b.name_jp,
    image_url: b.image_url,
  }));
  // tier_list (マップ指定があればそのマップで、 なければプール全体平均で _avgTier 使用)
  if (mapObj && mapObj.tier_list) {
    const tierByName = {};
    for (const t of mapObj.tier_list) tierByName[t.brawler] = t;
    pool = pool.map(b => ({
      ...b,
      tier: tierByName[b.name]?.tier || null,
      win_rate: tierByName[b.name]?.win_rate || null,
      picks: tierByName[b.name]?.picks || 0,
    }));
  } else {
    // 全マップ加重平均から _avgTier を取り出し
    computeBrawlerExtras();
    pool = pool.map(b => {
      const src = DB.brawlers.find(x => x.name === b.name);
      return { ...b, tier: src?._avgTier || null, win_rate: src?._weightedWr || null };
    });
  }
  // フィルタ
  if (tierFilter === "pool") pool = pool.filter(b => b.tier);
  else if (tierFilter === "A+") pool = pool.filter(b => b.tier && TIER_RANK[b.tier] >= 3);
  else if (tierFilter === "S+S") pool = pool.filter(b => b.tier === "S+" || b.tier === "S");
  else if (tierFilter === "Sp") pool = pool.filter(b => b.tier === "S+");
  return pool;
}

function spinRoulette() {
  const pool = _rouletteCandidates();
  const result = document.getElementById("roulette-result");
  if (!result) return;
  if (pool.length < 3) {
    result.innerHTML = `<div class="bg-yellow-900/30 border border-yellow-700 p-4 rounded text-yellow-200">候補が3人未満です。 対象を緩めてください (現在 ${pool.length}人)</div>`;
    return;
  }
  // 確定する3人を先に決定 (重複なし)
  const shuffled = [...pool].sort(() => Math.random() - 0.5);
  const finals = shuffled.slice(0, 3);

  // アニメーション: 3スロットを 50ms ごとにランダム表示、 順番に止める
  const totalDuration = 1800;  // ms
  const stopAt = [800, 1200, 1800];
  const intervals = [];

  function makeSlot(i, b) {
    return `<div data-slot="${i}" class="bg-gray-700 rounded p-3 text-center">
      ${b.image_url ? `<img src="${b.image_url}" class="w-full max-w-[120px] mx-auto rounded mb-2">` : '<div class="w-full aspect-square max-w-[120px] mx-auto bg-gray-600 rounded mb-2"></div>'}
      <div class="font-bold truncate" data-name>${escapeHtml(b.name_jp || b.name)}</div>
      ${b.tier ? `<div class="mt-1"><span class="px-2 py-0.5 rounded text-xs font-bold ${TIER_COLORS[b.tier] || ''}">${b.tier}</span> ${b.win_rate != null ? `<span class="text-xs text-gray-400 ml-1">${(b.win_rate*100).toFixed(0)}%</span>` : ""}</div>` : ""}
    </div>`;
  }

  // 初期描画 (ランダム)
  const init = [
    pool[Math.floor(Math.random() * pool.length)],
    pool[Math.floor(Math.random() * pool.length)],
    pool[Math.floor(Math.random() * pool.length)],
  ];
  result.innerHTML = `
    <div class="bg-gray-800 p-4 rounded">
      <div class="grid grid-cols-3 gap-2" id="roulette-slots">
        ${init.map((b, i) => makeSlot(i, b)).join("")}
      </div>
    </div>`;

  const t0 = Date.now();
  for (let i = 0; i < 3; i++) {
    intervals[i] = setInterval(() => {
      const elapsed = Date.now() - t0;
      const slotEl = result.querySelector(`[data-slot="${i}"]`);
      if (!slotEl) return;
      if (elapsed >= stopAt[i]) {
        clearInterval(intervals[i]);
        slotEl.outerHTML = makeSlot(i, finals[i]);
        if (i === 2) onRouletteFinish(finals);
        return;
      }
      const random = pool[Math.floor(Math.random() * pool.length)];
      slotEl.outerHTML = makeSlot(i, random);
    }, 60);
  }
}

function onRouletteFinish(finals) {
  // 最終確定の演出 + 補足情報 (もし マップ指定あれば トリオ全体勝率を表示)
  const mapHash = document.getElementById("roulette-map")?.value || "";
  const mapObj = mapHash ? DB.maps.find(m => m.hash === mapHash) : null;
  let trioInfo = "";
  if (mapObj && mapObj.all_trios) {
    const targetSet = new Set(finals.map(b => b.name));
    const match = mapObj.all_trios.find(t => {
      if (t.members.length !== 3) return false;
      const ts = new Set(t.members.map(m => m.brawler));
      if (ts.size !== 3) return false;
      for (const x of targetSet) if (!ts.has(x)) return false;
      return true;
    });
    if (match) {
      trioInfo = `<div class="mt-3 p-3 bg-green-900/30 border border-green-700 rounded text-sm">
        🎯 この3人組のデータあり: <span class="font-bold text-green-300">${(match.win_rate * 100).toFixed(0)}%</span> TOP2 (${match.picks}戦, 1位${match.rank1_count || 0} / 2位${match.rank2_count || 0})
      </div>`;
    } else {
      trioInfo = `<div class="mt-3 p-3 bg-gray-700/30 rounded text-xs text-gray-400">この3人組の過去データなし (5戦未満 or 未試行)</div>`;
    }
  }
  const result = document.getElementById("roulette-result");
  if (result && trioInfo) {
    result.querySelector(".bg-gray-800")?.insertAdjacentHTML("beforeend", trioInfo);
  }
}


// ============================================================
// クラブ集計
// ============================================================

function setupClub() {
  const tagInput = document.getElementById("club-tag");
  const btn = document.getElementById("club-search");
  const suggest = document.getElementById("club-suggest");
  if (!tagInput || !btn) return;
  const saved = localStorage.getItem("club_tag");
  if (saved) tagInput.value = saved;
  btn.addEventListener("click", () => { hideSuggest(suggest); fetchClub(tagInput.value); });
  tagInput.addEventListener("keydown", e => {
    if (e.key === "Enter") { hideSuggest(suggest); fetchClub(tagInput.value); }
    else if (e.key === "Escape") hideSuggest(suggest);
  });
  attachNameSuggest(tagInput, suggest, "clubs", item => {
    tagInput.value = item.tag;
    hideSuggest(suggest);
    fetchClub(item.tag);
  });
}

async function fetchClub(rawTag) {
  const tag = normalizeTag(rawTag);
  if (!tag || tag.length < 4) {
    document.getElementById("club-detail").innerHTML =
      '<div class="bg-red-900/30 border border-red-700 p-4 rounded text-red-200">クラブタグを入力してください</div>';
    return;
  }
  localStorage.setItem("club_tag", tag);
  document.getElementById("club-tag").value = tag;
  document.getElementById("club-detail").innerHTML =
    '<div class="bg-gray-800 p-6 rounded text-center text-gray-400">読込中...</div>';
  try {
    const res = await fetch(`${API_HOST}/api/club/${encodeURIComponent(tag)}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderClub(data);
  } catch (e) {
    document.getElementById("club-detail").innerHTML =
      `<div class="bg-red-900/30 border border-red-700 p-4 rounded text-red-200">取得失敗: ${escapeHtml(e.message)}</div>`;
  }
}

function renderClub(c) {
  const trackedMembers = c.members.filter(m => m.tracked);
  const untrackedMembers = c.members.filter(m => !m.tracked);
  // tracked を勝率順にソート
  trackedMembers.sort((a, b) => {
    const aWr = a.summary.total ? a.summary.top2 / a.summary.total : 0;
    const bWr = b.summary.total ? b.summary.top2 / b.summary.total : 0;
    return bWr - aWr;
  });
  untrackedMembers.sort((a, b) => (b.trophies || 0) - (a.trophies || 0));

  const renderRow = (m, idx) => {
    const s = m.summary;
    const wr = s.total ? (s.top2 / s.total * 100).toFixed(1) + "%" : "—";
    const r1 = s.total ? (s.rank1 / s.total * 100).toFixed(1) + "%" : "—";
    const ar = s.avg_rank ? s.avg_rank.toFixed(2) : "—";
    const wrColor = s.total
      ? (s.top2 / s.total >= 0.6 ? "text-green-300 font-bold"
        : s.top2 / s.total >= 0.5 ? "text-yellow-300"
        : "text-gray-300")
      : "text-gray-500";
    return `<tr class="border-b border-gray-700/50 hover:bg-gray-700/30 cursor-pointer" onclick="openMypageFromClub('${escapeHtml(m.tag)}')">
      <td class="py-2 px-2 text-gray-500 text-xs">${idx + 1}</td>
      <td class="py-2 px-2 truncate max-w-[120px]" title="${escapeHtml(m.name)}">${escapeHtml(m.name)}</td>
      <td class="py-2 px-2 text-xs text-gray-400 hidden sm:table-cell">${escapeHtml(m.role)}</td>
      <td class="py-2 px-2 text-right text-yellow-400 font-mono text-xs">🏆${m.trophies.toLocaleString()}</td>
      <td class="py-2 px-2 text-right font-mono text-xs">${s.total || "—"}</td>
      <td class="py-2 px-2 text-right font-mono text-xs ${wrColor}">${wr}</td>
      <td class="py-2 px-2 text-right font-mono text-xs hidden sm:table-cell">${r1}</td>
      <td class="py-2 px-2 text-right font-mono text-xs hidden md:table-cell">${ar}</td>
    </tr>`;
  };

  document.getElementById("club-detail").innerHTML = `
    <div class="bg-gray-800 p-4 rounded mb-4">
      <h2 class="text-xl font-bold">${escapeHtml(c.name)}</h2>
      <div class="text-sm text-gray-400 font-mono mt-1">${escapeHtml(c.tag)} · 🏆${c.trophies.toLocaleString()} · ${c.member_count}人 · ${escapeHtml(c.type)}</div>
      ${c.description ? `<div class="text-xs text-gray-500 mt-2">${escapeHtml(c.description)}</div>` : ""}
    </div>

    <div class="bg-gray-800 p-4 rounded mb-4">
      <h3 class="text-sm font-bold mb-2 text-gray-300 uppercase tracking-wide">取得済メンバー (${trackedMembers.length}人) - 勝率順</h3>
      ${trackedMembers.length === 0 ? '<div class="text-gray-500 text-sm">まだ誰もマイページで検索されていません。 各メンバーのタグをマイページで検索すると、 ここに統計が出ます。</div>' :
        `<div class="overflow-x-auto -mx-2"><table class="w-full text-sm">
          <thead><tr class="text-left text-xs text-gray-400 border-b border-gray-700">
            <th class="pb-2 px-2">#</th>
            <th class="pb-2 px-2">名前</th>
            <th class="pb-2 px-2 hidden sm:table-cell">役職</th>
            <th class="pb-2 px-2 text-right">トロ</th>
            <th class="pb-2 px-2 text-right">試合</th>
            <th class="pb-2 px-2 text-right">TOP2率</th>
            <th class="pb-2 px-2 text-right hidden sm:table-cell">1位率</th>
            <th class="pb-2 px-2 text-right hidden md:table-cell">平均順</th>
          </tr></thead>
          <tbody>${trackedMembers.map(renderRow).join("")}</tbody>
        </table></div>`}
    </div>

    ${untrackedMembers.length > 0 ? `
      <div class="bg-gray-800 p-4 rounded mb-4">
        <details>
          <summary class="cursor-pointer text-sm text-gray-400 hover:text-gray-200">未取得メンバー ${untrackedMembers.length}人 (クリックで展開)</summary>
          <table class="w-full text-sm mt-2">
            <tbody>${untrackedMembers.map((m, i) => `
              <tr class="border-b border-gray-700/50 hover:bg-gray-700/30 cursor-pointer" onclick="openMypageFromClub('${escapeHtml(m.tag)}')">
                <td class="py-2 px-2 text-gray-500 text-xs">${i + 1}</td>
                <td class="py-2 px-2">${escapeHtml(m.name)}</td>
                <td class="py-2 px-2 text-xs text-gray-400">${escapeHtml(m.role)}</td>
                <td class="py-2 px-2 text-right text-yellow-400 font-mono text-xs">🏆${m.trophies.toLocaleString()}</td>
              </tr>`).join("")}</tbody>
          </table>
          <div class="text-xs text-gray-500 mt-2">行をクリック → マイページで自動検索 (= ウォッチリスト追加 + 過去履歴import)</div>
        </details>
      </div>` : ""}`;
}

function openMypageFromClub(tag) {
  openMypage(tag);
}

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

// ============================================================
// マッチング時間 実測 (B案: battlelog 高頻度ポーリングで queue_seconds 推定)
// ============================================================
let QUEUE_CURRENT_ID = null;
let QUEUE_POLL_TIMER = null;
let QUEUE_LAST_TAG = "";

function setupQueue() {
  const input = document.getElementById("queue-tag");
  const startBtn = document.getElementById("queue-start");
  const suggest = document.getElementById("queue-suggest");
  if (!input || !startBtn) return;
  // 前回のタグを復元
  QUEUE_LAST_TAG = localStorage.getItem("queue_last_tag") || "";
  if (QUEUE_LAST_TAG) input.value = QUEUE_LAST_TAG;
  attachNameSuggest(input, suggest, "players", r => {
    input.value = r.tag;
    hideSuggest(suggest);
  });
  startBtn.addEventListener("click", () => {
    const raw = input.value.trim();
    if (!raw) return;
    // 名前で入力された場合は警告 (タグが必要)
    if (!raw.startsWith("#") && !/^[A-Z0-9]+$/i.test(raw)) {
      alert("プレイヤータグ (#XXXXXXX) を入力してください。 名前から検索する場合はサジェストから選択してください。");
      return;
    }
    const tag = normalizeTag(raw);
    QUEUE_LAST_TAG = tag;
    localStorage.setItem("queue_last_tag", tag);
    queueStart(tag);
  });
  input.addEventListener("keydown", e => {
    if (e.key === "Enter") startBtn.click();
  });
  // タブ切替時に履歴を読み込む
  document.querySelectorAll('.tab-btn[data-tab="queue"]').forEach(b => {
    b.addEventListener("click", () => {
      if (QUEUE_LAST_TAG) queueLoadHistory(QUEUE_LAST_TAG);
      if (QUEUE_CURRENT_ID) queuePollStatus();
    });
  });
}

async function queueStart(tag) {
  const statusEl = document.getElementById("queue-status");
  statusEl.innerHTML = `<div class="text-sm text-yellow-400">⏳ 計測開始中...</div>`;
  try {
    const url = `${API_HOST}/api/queue/start?tag=${encodeURIComponent(tag)}`;
    const res = await fetch(url, { method: "POST" });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      statusEl.innerHTML = `<div class="text-sm text-red-400">エラー: ${escapeHtml(errBody.detail || res.status)}</div>`;
      return;
    }
    const data = await res.json();
    QUEUE_CURRENT_ID = data.measurement_id;
    statusEl.dataset.startedAt = data.queue_start_at;
    if (QUEUE_POLL_TIMER) clearInterval(QUEUE_POLL_TIMER);
    renderQueueStatus({ status: "pending", queue_start_at: data.queue_start_at, tag });
    QUEUE_POLL_TIMER = setInterval(queuePollStatus, 5000);
    queueLoadHistory(tag);
  } catch (e) {
    statusEl.innerHTML = `<div class="text-sm text-red-400">通信エラー: ${escapeHtml(String(e))}</div>`;
  }
}

async function queuePollStatus() {
  if (!QUEUE_CURRENT_ID) return;
  try {
    const res = await fetch(`${API_HOST}/api/queue/${QUEUE_CURRENT_ID}`);
    if (!res.ok) return;
    const m = await res.json();
    renderQueueStatus(m);
    if (m.status !== "pending") {
      if (QUEUE_POLL_TIMER) { clearInterval(QUEUE_POLL_TIMER); QUEUE_POLL_TIMER = null; }
      QUEUE_CURRENT_ID = null;
      queueLoadHistory(m.tag);
    }
  } catch (e) { /* ignore transient */ }
}

function renderQueueStatus(m) {
  const el = document.getElementById("queue-status");
  if (!el) return;
  const now = Math.floor(Date.now() / 1000);
  const startedAt = m.queue_start_at;
  const elapsed = now - startedAt;
  if (m.status === "pending") {
    el.innerHTML = `
      <div class="bg-gray-900 border border-yellow-700/50 rounded p-3">
        <div class="text-sm font-semibold text-yellow-400 mb-1">⏱ 計測中... <span class="font-mono">${formatSec(elapsed)}</span></div>
        <div class="text-xs text-gray-400">${escapeHtml(m.tag)} · 開始: ${formatLocalTime(startedAt)}</div>
        <div class="text-xs text-gray-500 mt-2">サーバが12秒ごとに新試合をチェックしています。 30分でタイムアウト。</div>
      </div>`;
  } else if (m.status === "matched") {
    const qs = m.queue_seconds || 0;
    const qsColor = qs < 60 ? "text-green-400" : qs < 180 ? "text-yellow-400" : qs < 400 ? "text-orange-400" : "text-red-400";
    el.innerHTML = `
      <div class="bg-gray-900 border border-green-700/50 rounded p-3">
        <div class="text-base font-bold ${qsColor}">✓ マッチ検出: <span class="font-mono">${qs}s</span> 待ち</div>
        <div class="text-xs text-gray-300 mt-1">
          モード: <b>${escapeHtml(m.mode || "?")}</b> · マップ: ${escapeHtml(m.map || "?")} · ブロウラー: ${escapeHtml(m.brawler || "?")}
        </div>
        <div class="text-xs text-gray-500 mt-1">試合時間 ${m.duration}s · 検出: ${formatLocalTime(m.detected_at)}</div>
      </div>`;
  } else if (m.status === "timeout") {
    el.innerHTML = `
      <div class="bg-gray-900 border border-red-700/50 rounded p-3">
        <div class="text-sm font-semibold text-red-400">✗ タイムアウト (30分間に試合が検出されませんでした)</div>
        <div class="text-xs text-gray-500 mt-1">フレンド戦・トレーニング・キュー キャンセル等は記録されません。</div>
      </div>`;
  } else if (m.status === "canceled") {
    el.innerHTML = `<div class="text-sm text-gray-400">計測キャンセル: ${escapeHtml(m.notes || "")}</div>`;
  }
}

function formatSec(s) {
  s = Math.max(0, Math.floor(s));
  const m = Math.floor(s / 60), sec = s % 60;
  return m > 0 ? `${m}m ${sec.toString().padStart(2, "0")}s` : `${sec}s`;
}

function formatLocalTime(unixSec) {
  if (!unixSec) return "—";
  const d = new Date(unixSec * 1000);
  return d.toLocaleTimeString("ja-JP", { hour12: false });
}

async function queueLoadHistory(tag) {
  const el = document.getElementById("queue-history");
  if (!el || !tag) return;
  try {
    const res = await fetch(`${API_HOST}/api/queue/recent/${encodeURIComponent(tag)}?limit=30`);
    if (!res.ok) return;
    const data = await res.json();
    const ms = (data.measurements || []).filter(m => m.status === "matched");
    if (ms.length === 0) {
      el.innerHTML = `<div class="bg-gray-800 p-4 rounded text-sm text-gray-500">${escapeHtml(tag)} の計測履歴はまだありません。</div>`;
      return;
    }
    // 統計
    const qsList = ms.map(m => m.queue_seconds).sort((a,b) => a-b);
    const median = qsList[Math.floor(qsList.length/2)];
    const mean = Math.round(qsList.reduce((a,b)=>a+b,0) / qsList.length);
    const min = qsList[0], max = qsList[qsList.length-1];
    // モード別中央値
    const byMode = {};
    ms.forEach(m => { if (!byMode[m.mode]) byMode[m.mode] = []; byMode[m.mode].push(m.queue_seconds); });
    const modeStats = Object.entries(byMode).map(([mode, arr]) => {
      arr.sort((a,b)=>a-b);
      return { mode, n: arr.length, median: arr[Math.floor(arr.length/2)] };
    }).sort((a,b) => b.n - a.n);
    // ブロウラー別中央値 (3戦以上のみ)
    const byBr = {};
    ms.forEach(m => { if (!byBr[m.brawler]) byBr[m.brawler] = []; byBr[m.brawler].push(m.queue_seconds); });
    const brStats = Object.entries(byBr).filter(([,a]) => a.length >= 3).map(([br, arr]) => {
      arr.sort((a,b)=>a-b);
      return { br, n: arr.length, median: arr[Math.floor(arr.length/2)] };
    }).sort((a,b) => b.median - a.median);
    el.innerHTML = `
      <div class="bg-gray-800 p-4 rounded mb-4">
        <h3 class="text-sm font-bold mb-2 text-gray-300 uppercase tracking-wide">${escapeHtml(tag)} 計測サマリ (N=${ms.length})</h3>
        <div class="grid grid-cols-4 gap-2 text-center mb-3">
          <div class="bg-gray-900 p-2 rounded"><div class="text-xs text-gray-500">中央値</div><div class="text-lg font-bold text-yellow-400">${median}s</div></div>
          <div class="bg-gray-900 p-2 rounded"><div class="text-xs text-gray-500">平均</div><div class="text-lg font-bold">${mean}s</div></div>
          <div class="bg-gray-900 p-2 rounded"><div class="text-xs text-gray-500">最短</div><div class="text-lg font-bold text-green-400">${min}s</div></div>
          <div class="bg-gray-900 p-2 rounded"><div class="text-xs text-gray-500">最長</div><div class="text-lg font-bold text-red-400">${max}s</div></div>
        </div>
        ${modeStats.length > 0 ? `
          <div class="mt-3">
            <div class="text-xs text-gray-400 mb-1">モード別 中央値</div>
            <div class="flex flex-wrap gap-1">
              ${modeStats.map(s => `<span class="px-2 py-1 bg-gray-900 rounded text-xs">${escapeHtml(s.mode)}: <b>${s.median}s</b> <span class="text-gray-500">(N=${s.n})</span></span>`).join("")}
            </div>
          </div>` : ""}
        ${brStats.length > 0 ? `
          <div class="mt-3">
            <div class="text-xs text-gray-400 mb-1">ブロウラー別 中央値 (3戦以上、遅い順)</div>
            <div class="flex flex-wrap gap-1">
              ${brStats.slice(0, 20).map(s => {
                const c = s.median < 100 ? "text-green-400" : s.median < 250 ? "text-yellow-400" : "text-red-400";
                return `<span class="px-2 py-1 bg-gray-900 rounded text-xs">${escapeHtml(s.br)}: <b class="${c}">${s.median}s</b> <span class="text-gray-500">(N=${s.n})</span></span>`;
              }).join("")}
            </div>
          </div>` : ""}
      </div>
      <div class="bg-gray-800 p-4 rounded mb-4">
        <h3 class="text-sm font-bold mb-2 text-gray-300 uppercase tracking-wide">直近 ${ms.length} 戦</h3>
        <div class="overflow-x-auto -mx-2">
          <table class="w-full text-sm">
            <thead><tr class="text-left text-xs text-gray-400 border-b border-gray-700">
              <th class="pb-1 px-2">時刻</th>
              <th class="pb-1 px-2 text-right">待ち</th>
              <th class="pb-1 px-2">モード</th>
              <th class="pb-1 px-2">マップ</th>
              <th class="pb-1 px-2">ブロウラー</th>
            </tr></thead>
            <tbody>${ms.slice(0, 50).map(m => {
              const qs = m.queue_seconds || 0;
              const qsc = qs < 60 ? "text-green-400" : qs < 180 ? "text-yellow-400" : qs < 400 ? "text-orange-400" : "text-red-400";
              return `<tr class="border-b border-gray-700/50">
                <td class="py-1 px-2 text-xs text-gray-400">${formatLocalTime(m.queue_start_at)}</td>
                <td class="py-1 px-2 text-right font-mono ${qsc}">${qs}s</td>
                <td class="py-1 px-2 text-xs">${escapeHtml(m.mode || "?")}</td>
                <td class="py-1 px-2 text-xs">${escapeHtml(m.map || "?")}</td>
                <td class="py-1 px-2 text-xs">${escapeHtml(m.brawler || "?")}</td>
              </tr>`;
            }).join("")}</tbody>
          </table>
        </div>
      </div>`;
  } catch (e) { /* ignore */ }
}

// ============================================================
// 練習試合 bot バトルカード観察記録 (ユーザ手動入力 → MMR推定)
// ============================================================
const BOT_RANK_OPTIONS = [
  "Bronze I", "Bronze II", "Bronze III",
  "Silver I", "Silver II", "Silver III",
  "Gold I", "Gold II", "Gold III",
  "Diamond I", "Diamond II", "Diamond III",
  "Mythic I", "Mythic II", "Mythic III",
  "Legendary I", "Legendary II", "Legendary III",
  "Masters",
  "Pro",
];

let BOT_OBS_CACHE = {};  // tag → {observations, fetched_at}

function renderMypageBotObs(tag, profile) {
  // 自分の rankedRankName を表示 (比較基準)
  const myRank = profile && profile.rankedRankName ? profile.rankedRankName : (LANG === "en" ? "(no ranked play)" : "(ガチ未プレイ)");
  const myElo = profile && profile.rankedElo != null ? profile.rankedElo : 0;
  // 自分の brawlers から prestige 一覧 (上位3個 表示)
  const myBrawlers = profile && profile.brawlers ? profile.brawlers : [];
  // ブロウラー候補 (リスト)
  // 入力フォーム + 履歴一覧
  const cache = BOT_OBS_CACHE[tag];
  let listHtml = `<div class="text-sm text-gray-500">${LANG === "en" ? "Loading observations..." : "履歴を読み込み中..."}</div>`;
  if (cache) {
    if (cache.observations.length === 0) {
      listHtml = `<div class="text-sm text-gray-500">${LANG === "en" ? "No bot observations yet." : "観察記録はまだありません。 練習試合で確認した bot のカード値を入力してください。"}</div>`;
    } else {
      // 統計
      const obs = cache.observations;
      const withRank = obs.filter(o => o.bot_ranked_rank_num);
      const withPrestige = obs.filter(o => o.bot_prestige_level != null);
      const myRankNum = BOT_RANK_OPTIONS.indexOf(myRank) + 1;  // 0なら未プレイ
      let statHtml = "";
      if (withRank.length > 0) {
        const ranks = withRank.map(o => o.bot_ranked_rank_num).sort((a,b)=>a-b);
        const medRank = ranks[Math.floor(ranks.length/2)];
        const medRankName = BOT_RANK_OPTIONS[medRank - 1] || "?";
        const diff = myRankNum ? (medRank - myRankNum) : null;
        statHtml += `<div class="bg-gray-900 p-2 rounded text-sm">
          <b>${LANG === "en" ? "Bot ranked rank median" : "bot rankedRank 中央値"}:</b> ${escapeHtml(medRankName)}
          ${myRankNum ? ` <span class="text-gray-400">(${LANG === "en" ? "you" : "自分"}: ${escapeHtml(myRank)}, diff ${diff >= 0 ? "+" : ""}${diff})</span>` : ""}
        </div>`;
      }
      if (withPrestige.length > 0) {
        const pres = withPrestige.map(o => o.bot_prestige_level).sort((a,b)=>a-b);
        const medP = pres[Math.floor(pres.length/2)];
        statHtml += `<div class="bg-gray-900 p-2 rounded text-sm mt-1">
          <b>${LANG === "en" ? "Bot prestige median" : "bot prestige 中央値"}:</b> ${medP}
        </div>`;
      }
      listHtml = `${statHtml}
        <table class="w-full text-sm mt-3">
          <thead><tr class="text-left text-xs text-gray-400 border-b border-gray-700">
            <th class="pb-1 px-1">${LANG === "en" ? "Time" : "日時"}</th>
            <th class="pb-1 px-1">${LANG === "en" ? "Bot brawler" : "botキャラ"}</th>
            <th class="pb-1 px-1 text-right">Prestige</th>
            <th class="pb-1 px-1">Rank</th>
            <th class="pb-1 px-1"></th>
          </tr></thead>
          <tbody>${obs.map(o => `
            <tr class="border-b border-gray-700/50">
              <td class="py-1 px-1 text-xs text-gray-400">${new Date(o.observed_at * 1000).toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</td>
              <td class="py-1 px-1 text-xs">${escapeHtml(o.bot_brawler || "—")}</td>
              <td class="py-1 px-1 text-right text-xs">${o.bot_prestige_level != null ? o.bot_prestige_level : "—"}</td>
              <td class="py-1 px-1 text-xs">${escapeHtml(o.bot_ranked_rank_name || "—")}</td>
              <td class="py-1 px-1 text-right">
                <button onclick="deleteBotObs(${o.id}, '${escapeHtml(tag)}')" class="text-xs text-red-400 hover:text-red-300">×</button>
              </td>
            </tr>`).join("")}</tbody>
        </table>`;
    }
  } else {
    // fetch in background
    fetchBotObs(tag);
  }
  return `
    <div class="bg-gray-800 p-4 rounded mb-4">
      <h3 class="text-sm font-bold mb-2 text-gray-300 uppercase tracking-wide">${LANG === "en" ? "Record practice match bot battle card" : "練習試合 bot バトルカード記録"}</h3>
      <div class="text-xs text-gray-400 mb-3 leading-relaxed">
        ${LANG === "en"
          ? "Open a brawler's detail page → tap 'Practice Match' → observe the bot's battle card (prestige level + ranked rank) → enter here. Comparing across players estimates which MMR band the bot reflects."
          : "ブロウラー詳細画面 → 「練習試合」 ボタン → 出てきた bot のバトルカードを目視確認 → prestigeLevel と rankedRank を入力。 観察値を蓄積すれば、 bot が反映している MMR帯が見えてきます。"}<br>
        ${LANG === "en" ? "Your ranked rank:" : "あなたの現ガチランク:"} <b>${escapeHtml(myRank)}</b> ${myElo ? `(Elo ${myElo})` : ""}
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <div>
          <label class="text-xs text-gray-400 block mb-1">${LANG === "en" ? "Bot brawler" : "bot キャラ"}</label>
          <input id="botobs-brawler" placeholder="${LANG === "en" ? "e.g. FRANK" : "例: FRANK"}" class="w-full p-2 bg-gray-900 border border-gray-700 rounded text-sm font-mono">
        </div>
        <div>
          <label class="text-xs text-gray-400 block mb-1">Prestige</label>
          <input id="botobs-prestige" type="number" min="0" max="50" placeholder="0-50" class="w-full p-2 bg-gray-900 border border-gray-700 rounded text-sm font-mono">
        </div>
        <div class="col-span-2 sm:col-span-1">
          <label class="text-xs text-gray-400 block mb-1">Ranked rank</label>
          <select id="botobs-rank" class="w-full p-2 bg-gray-900 border border-gray-700 rounded text-sm">
            <option value="">—</option>
            ${BOT_RANK_OPTIONS.map(r => `<option value="${r}">${r}</option>`).join("")}
          </select>
        </div>
        <div class="col-span-2 sm:col-span-1 self-end">
          <button onclick="submitBotObs('${escapeHtml(tag)}')" class="w-full py-2 bg-green-600 hover:bg-green-500 rounded text-sm font-semibold">
            ${LANG === "en" ? "Save" : "保存"}
          </button>
        </div>
      </div>
      <div id="botobs-msg" class="mt-2 text-xs"></div>
    </div>
    <div class="bg-gray-800 p-4 rounded mb-4">
      <h3 class="text-sm font-bold mb-2 text-gray-300 uppercase tracking-wide">${LANG === "en" ? "Observation history" : "観察履歴"}</h3>
      <div id="botobs-list">${listHtml}</div>
    </div>`;
}

async function fetchBotObs(tag) {
  try {
    const res = await fetch(`${API_HOST}/api/bot-obs/${encodeURIComponent(tag)}?limit=200`);
    if (!res.ok) return;
    const data = await res.json();
    BOT_OBS_CACHE[tag] = { observations: data.observations || [], fetched_at: Date.now() };
    if (MYPAGE_SECTION === "botobs" && MYPAGE_DATA && MYPAGE_DATA.tag === tag) {
      renderMypage();
    }
  } catch (e) { /* ignore */ }
}

async function submitBotObs(tag) {
  const brawler = document.getElementById("botobs-brawler").value.trim().toUpperCase();
  const prestige = document.getElementById("botobs-prestige").value.trim();
  const rank = document.getElementById("botobs-rank").value.trim();
  const msg = document.getElementById("botobs-msg");
  if (!brawler && !prestige && !rank) {
    msg.innerHTML = `<span class="text-red-400">${LANG === "en" ? "Enter at least one field" : "少なくとも1項目入力してください"}</span>`;
    return;
  }
  const params = new URLSearchParams();
  params.set("tag", tag);
  if (brawler) params.set("bot_brawler", brawler);
  if (prestige) params.set("bot_prestige_level", prestige);
  if (rank) params.set("bot_ranked_rank_name", rank);
  msg.innerHTML = `<span class="text-gray-400">${LANG === "en" ? "Saving..." : "保存中..."}</span>`;
  try {
    const res = await fetch(`${API_HOST}/api/bot-obs?${params.toString()}`, { method: "POST" });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      msg.innerHTML = `<span class="text-red-400">Error: ${escapeHtml(errBody.detail || res.status)}</span>`;
      return;
    }
    msg.innerHTML = `<span class="text-green-400">${LANG === "en" ? "Saved" : "保存しました"}</span>`;
    document.getElementById("botobs-brawler").value = "";
    document.getElementById("botobs-prestige").value = "";
    document.getElementById("botobs-rank").value = "";
    delete BOT_OBS_CACHE[tag];
    await fetchBotObs(tag);
  } catch (e) {
    msg.innerHTML = `<span class="text-red-400">Network error</span>`;
  }
}

async function deleteBotObs(obsId, tag) {
  if (!confirm(LANG === "en" ? "Delete this observation?" : "この観察記録を削除しますか?")) return;
  try {
    const url = `${API_HOST}/api/bot-obs/${obsId}?tag=${encodeURIComponent(tag)}`;
    const res = await fetch(url, { method: "DELETE" });
    if (res.ok) {
      delete BOT_OBS_CACHE[tag];
      await fetchBotObs(tag);
    }
  } catch (e) { /* ignore */ }
}

load();
