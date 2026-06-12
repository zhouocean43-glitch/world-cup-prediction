const state = {
  timeline: [],
  filter: "all",
};

const DEFAULT_TOURNAMENT_SEED = 42;

const els = {
  updatedAt: document.querySelector("#updatedAt"),
  updatedContext: document.querySelector("#updatedContext"),
  providerNote: document.querySelector("#providerNote"),
  timeline: document.querySelector("#timeline"),
  filters: document.querySelector("#filters"),
  featuredMatch: document.querySelector("#featuredMatch"),
  championList: document.querySelector("#championList"),
  championStatus: document.querySelector("#championStatus"),
  rerunTournament: document.querySelector("#rerunTournament"),
};

function pct(value, digits = 0) {
  return `${(value * 100).toFixed(digits)}%`;
}

function formatDate(iso) {
  const date = new Date(iso);
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    weekday: "short",
  }).format(date);
}

function formatTime(iso) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

function formatUpdatedParts(iso) {
  if (!iso) return { time: "--:--", date: "等待刷新" };
  const date = new Date(iso);
  return {
    time: new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date),
    date: `${new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
    }).format(date)} 北京时间`,
  };
}

function formatDateTime(iso) {
  if (!iso) return "未生成";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`请求失败：${response.status}`);
  return response.json();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function strongestFixtureScore(item) {
  return item.prediction.team_a.elo + item.prediction.team_b.elo;
}

function oddsPart(label, value, movement = 0) {
  const direction = movement > 0 ? "up" : movement < 0 ? "down" : "flat";
  const arrow = movement > 0 ? "▲" : movement < 0 ? "▼" : "•";
  const delta = movement === 0 ? "0.00" : Math.abs(movement).toFixed(2);
  return `
    <span class="odds-part ${direction}">
      <em>${label}</em>
      <b>${value.toFixed(2)} 倍</b>
      <small>${arrow}${delta}</small>
    </span>
  `;
}

function oddsLine(signal, item) {
  const odds = signal.market_odds;
  const movement = signal.odds_movement || {};
  const labels = item
    ? [`${item.team_a_name}胜`, "平局", `${item.team_b_name}胜`]
    : ["A胜", "平局", "B胜"];
  return `
    <span class="odds-line">
      ${oddsPart(labels[0], odds.team_a, movement.team_a || 0)}
      ${oddsPart(labels[1], odds.draw, movement.draw || 0)}
      ${oddsPart(labels[2], odds.team_b, movement.team_b || 0)}
    </span>
  `;
}

function marketLabel(signal) {
  if (signal.market_type === "bookmaker_aggregate") {
    const count = signal.bookmaker_count || 0;
    return count ? `市场均赔 · ${count} 家报价` : "市场均赔";
  }
  if (signal.market_type === "bookmaker_snapshot") return "盘口快照";
  return "暂无市场盘口";
}

function bookmakerSummary(signal) {
  if (signal.bookmakers && signal.bookmakers.length) {
    return signal.bookmakers.slice(0, 4).join("、");
  }
  if (signal.market_type === "model_placeholder") return "暂无公开报价";
  return signal.source;
}

function goalMarketText(signal) {
  const goalMarket = signal.goal_market;
  if (!goalMarket || !goalMarket.total_goals) return "";
  return ` · 总进球 ${Number(goalMarket.total_goals).toFixed(2)}`;
}

function googleNewsUrl(query) {
  return `https://news.google.com/search?q=${encodeURIComponent(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans`;
}

function matchNewsQuery(item, extra = "") {
  return `${item.team_a_name} ${item.team_b_name} World Cup ${extra}`.trim();
}

function newsLink(label, query, className = "news-link") {
  return `
    <a class="${className}" href="${googleNewsUrl(query)}" target="_blank" rel="noopener noreferrer">
      ${escapeHtml(label)}
    </a>
  `;
}

function newsActions(item) {
  return `
    <div class="news-actions">
      ${newsLink("赛前新闻", matchNewsQuery(item, "preview news"), "news-pill")}
      ${newsLink("伤停动态", matchNewsQuery(item, "injury team news"), "news-pill")}
    </div>
  `;
}

function hasFinalResult(item) {
  return item.result && item.result.status === "final";
}

function resultScoreText(item) {
  if (!hasFinalResult(item)) return "";
  return `${item.result.team_a_goals}-${item.result.team_b_goals}`;
}

function outcomeKeyFromGoals(result) {
  if (result.team_a_goals > result.team_b_goals) return "team_a_win";
  if (result.team_a_goals < result.team_b_goals) return "team_b_win";
  return "draw";
}

function outcomeLabel(item, key) {
  if (key === "team_a_win") return `${item.team_a_name} 胜`;
  if (key === "team_b_win") return `${item.team_b_name} 胜`;
  return "平局";
}

function predictedOutcome(item) {
  const probs = item.prediction.probabilities;
  return Object.entries(probs).sort((left, right) => right[1] - left[1])[0][0];
}

function resultVerdict(item) {
  if (!hasFinalResult(item)) return "";
  const actual = outcomeKeyFromGoals(item.result);
  const predicted = predictedOutcome(item);
  const topScore = item.prediction.top_scorelines?.[0];
  const topText = topScore ? `模型首选 ${topScore.team_a_goals}-${topScore.team_b_goals}` : "模型首选待生成";
  return `${actual === predicted ? "方向命中" : "方向偏离"} · ${topText}`;
}

function finalScoreline(item) {
  if (!hasFinalResult(item)) return "";
  return `
    <span class="final-scoreline">
      <b>${item.team_a_flag} ${item.result.team_a_goals}</b>
      <i>FT</i>
      <b>${item.result.team_b_goals} ${item.team_b_flag}</b>
    </span>
    <small>${escapeHtml(resultVerdict(item))}</small>
  `;
}

function signalRow(label, value) {
  return `
    <div class="signal-row">
      <span>${escapeHtml(label)}</span>
      <b>${escapeHtml(value)}</b>
    </div>
  `;
}

function renderProviderStatus(status = {}, fallbackNote = "", updatedAt = "") {
  const connected = Boolean(status.connected);
  const matched = Number(status.matched || 0);
  const totalFixtures = Number(status.total_fixtures || state.timeline.length || matched || 0);
  const maxBookmakers = Number(status.max_bookmakers || 0);
  const calibration = status.calibration || (connected ? "盘口校准" : "模型占位");
  const bookmakerLabel = status.bookmaker_label
    ? status.bookmaker_label.replaceAll(" / ", " · ")
    : status.message || fallbackNote || "等待数据";
  const coverageLabel = connected && totalFixtures ? `${matched}/${totalFixtures}` : "--/--";
  const coverageText = connected
    ? `已接入 ${matched} 场公开盘口，其余场次保留模型占位。`
    : status.message || fallbackNote || "等待公开盘口。";
  const badge = connected ? "已同步" : status.configured ? "待盘口" : "本地模型";
  const updated = formatUpdatedParts(updatedAt);

  document.querySelector(".signal-top b").textContent = badge;
  els.updatedAt.textContent = coverageLabel;
  els.updatedContext.innerHTML = `<b>${escapeHtml(updated.time)}</b><span>${escapeHtml(updated.date)}</span>`;
  els.providerNote.innerHTML = `
    <p class="signal-summary">${escapeHtml(coverageText)}</p>
    <div class="signal-list">
      ${signalRow("盘口", connected ? `最多 ${maxBookmakers} 家均值` : "暂无公开报价")}
      ${signalRow("比分", connected ? "胜平负 + 大小球校准" : calibration)}
      ${signalRow("新闻", "赛前 / 伤停入口可点")}
    </div>
    <p class="signal-source">来源：${escapeHtml(bookmakerLabel)}</p>
  `;
}

function scorelinePicks(scorelines = [], limit = 3) {
  return `
    <div class="score-picks">
      ${scorelines
        .slice(0, limit)
        .map(
          (score, index) => `
            <span class="score-chip ${index === 0 ? "primary" : ""}">
              <b>${score.team_a_goals}-${score.team_b_goals}</b>
              <small>${pct(score.probability, 1)}</small>
            </span>
          `
        )
        .join("")}
    </div>
  `;
}

function filteredFixtures() {
  if (state.filter === "high") {
    return [...state.timeline]
      .sort((a, b) => strongestFixtureScore(b) - strongestFixtureScore(a))
      .slice(0, 16)
      .sort((a, b) => new Date(a.kickoff) - new Date(b.kickoff));
  }
  if (state.filter === "next") {
    return state.timeline.slice(0, 16);
  }
  return state.timeline;
}

function matchCard(item) {
  const probs = item.prediction.probabilities;
  const news = item.signal.news;
  const lean = item.prediction.lean;
  const isBalanced = lean === "balanced";
  const weather = item.weather || {};
  const label = marketLabel(item.signal);
  const isFinal = hasFinalResult(item);
  const actualOutcome = isFinal ? outcomeLabel(item, outcomeKeyFromGoals(item.result)) : "";

  return `
    <article class="match-card ${isFinal ? "is-final" : ""}">
      <div class="match-time">
        <strong>${formatTime(item.kickoff)}</strong>
        <span>G${item.group} · 第 ${item.matchday} 轮</span>
      </div>

      <div class="match-main">
        <div class="teams ${isFinal ? "finished" : ""}">
          <span>${item.team_a_flag} ${item.team_a_name}</span>
          <i>${isFinal ? resultScoreText(item) : "vs"}</i>
          <span>${item.team_b_flag} ${item.team_b_name}</span>
        </div>
        <div class="value-row">
          <span>${item.prediction.team_a.squad_value_label}</span>
          <b>球队总身价</b>
          <span>${item.prediction.team_b.squad_value_label}</span>
        </div>
        <div class="lean ${isFinal ? "result" : isBalanced ? "balanced" : ""}">
          ${isFinal ? `已完赛 · ${actualOutcome}` : isBalanced ? "均势" : `倾向 ${lean}`}
        </div>
      </div>

      <div class="prob-strip" style="--a:${probs.team_a_win * 100}%; --d:${probs.draw * 100}%; --b:${probs.team_b_win * 100}%">
        <span class="home" title="A 队胜"></span>
        <span class="draw" title="平局"></span>
        <span class="away" title="B 队胜"></span>
      </div>

      <div class="numbers">
        <span>A ${pct(probs.team_a_win)}</span>
        <span>平 ${pct(probs.draw)}</span>
        <span>B ${pct(probs.team_b_win)}</span>
      </div>

      <div class="meta-grid">
        ${
          isFinal
            ? `<div class="result-panel">
                <span>赛果</span>
                <strong>${finalScoreline(item)}</strong>
              </div>`
            : ""
        }
        <div>
          <span>${isFinal ? "赛前胜平负" : "胜平负"} · ${label}</span>
          <strong>${oddsLine(item.signal, item)}</strong>
        </div>
        <div>
          <span>${isFinal ? "赛前热门比分" : "热门比分"}${goalMarketText(item.signal)}</span>
          <strong>${scorelinePicks(item.prediction.top_scorelines)}</strong>
        </div>
        <div>
          <span>新闻信号</span>
          <strong>${news.team_a_absences + news.team_b_absences} 个缺阵风险</strong>
        </div>
        <div>
          <span>球场</span>
          <strong>${item.stadium}</strong>
        </div>
        <div>
          <span>地点</span>
          <strong>${item.city} · ${item.country}</strong>
        </div>
        <div>
          <span>天气</span>
          <strong>${weather.summary || "待刷新"}${weather.temperature_c ? ` · ${weather.temperature_c}°C` : ""}</strong>
        </div>
      </div>

      <ul class="news-list">
        <li>报价来源：${bookmakerSummary(item.signal)}</li>
        <li>${newsActions(item)}</li>
        ${(news.headlines || [])
          .slice(0, 2)
          .map((headline) => `<li>${newsLink(headline, `${matchNewsQuery(item)} ${headline}`)}</li>`)
          .join("")}
      </ul>
    </article>
  `;
}

function featuredCard(item) {
  const probs = item.prediction.probabilities;
  const weather = item.weather || {};
  const news = item.signal.news || {};
  const label = marketLabel(item.signal);
  const isFinal = hasFinalResult(item);

  return `
    <article class="featured-card ${isFinal ? "is-final" : ""}">
      <div class="fixture-block">
        <div class="fixture-time">
          <strong>${formatTime(item.kickoff)}</strong>
          <span>${formatDate(item.kickoff)} · G${item.group} 第 ${item.matchday} 轮</span>
        </div>
        <div class="venue-line">
          <span>${item.stadium}</span>
          <span>${item.city} · ${item.country}</span>
          <span>${weather.summary || "天气待刷新"}${weather.temperature_c ? ` · ${weather.temperature_c}°C` : ""}</span>
        </div>
      </div>

      <div class="featured-teams">
        <div class="featured-names ${isFinal ? "finished" : ""}">
          <span>${item.team_a_flag} ${item.team_a_name}</span>
          <i>${isFinal ? resultScoreText(item) : "vs"}</i>
          <span>${item.team_b_flag} ${item.team_b_name}</span>
        </div>
        <div class="featured-values">
          <span>${item.prediction.team_a.squad_value_label}</span>
          <b>球队总身价</b>
          <span>${item.prediction.team_b.squad_value_label}</span>
        </div>
        ${
          isFinal
            ? `<div class="result-badge">
                <span>已完赛</span>
                <strong>${escapeHtml(outcomeLabel(item, outcomeKeyFromGoals(item.result)))}</strong>
                <small>${escapeHtml(resultVerdict(item))}</small>
              </div>`
            : ""
        }
        <div class="prob-strip" style="--a:${probs.team_a_win * 100}%; --d:${probs.draw * 100}%; --b:${probs.team_b_win * 100}%">
          <span class="home"></span>
          <span class="draw"></span>
          <span class="away"></span>
        </div>
        <div class="featured-probs">
          <div class="prob-box"><span>${item.team_a_name} 胜</span><strong>${pct(probs.team_a_win)}</strong></div>
          <div class="prob-box"><span>平局</span><strong>${pct(probs.draw)}</strong></div>
          <div class="prob-box"><span>${item.team_b_name} 胜</span><strong>${pct(probs.team_b_win)}</strong></div>
        </div>
      </div>

      <div class="featured-side">
        <div class="metric-grid">
          ${
            isFinal
              ? `<div class="metric result-panel"><span>赛果</span><strong>${finalScoreline(item)}</strong></div>`
              : ""
          }
          <div class="metric"><span>${isFinal ? "赛前胜平负" : "胜平负"} · ${label}</span><strong>${oddsLine(item.signal, item)}</strong></div>
          <div class="metric"><span>${isFinal ? "赛前热门比分 Top 3" : "热门比分 Top 3"}${goalMarketText(item.signal)}</span><strong>${scorelinePicks(item.prediction.top_scorelines)}</strong></div>
          <div class="metric"><span>报价来源</span><strong>${bookmakerSummary(item.signal)}</strong></div>
          <div class="metric">
            <span>新闻</span>
            <strong>${newsLink((news.headlines || [])[0] || "查看赛前新闻", matchNewsQuery(item, "latest news"), "news-link featured-news-link")}</strong>
          </div>
        </div>
      </div>
    </article>
  `;
}

function renderTimeline() {
  const groups = new Map();
  for (const item of filteredFixtures()) {
    const day = formatDate(item.kickoff);
    if (!groups.has(day)) groups.set(day, []);
    groups.get(day).push(item);
  }

  els.timeline.innerHTML = [...groups.entries()]
    .map(
      ([day, fixtures]) => `
        <section class="day-block">
          <div class="day-marker">
            <span></span>
            <strong>${day}</strong>
          </div>
          <div class="match-list">
            ${fixtures.map(matchCard).join("")}
          </div>
        </section>
      `
    )
    .join("");
}

function renderFeatured() {
  if (!state.timeline.length) {
    els.featuredMatch.innerHTML = '<div class="loading">等待赛程加载...</div>';
    return;
  }
  els.featuredMatch.innerHTML = featuredCard(state.timeline[0]);
}

async function loadTimeline() {
  const data = await fetchJson("/api/timeline");
  state.timeline = data.fixtures;
  renderProviderStatus(data.provider_status, data.provider_note, data.updated_at);
  renderFeatured();
  renderTimeline();
}

function renderChampions(data) {
  const hasMarketFutures = data.market_futures && data.market_futures.length;
  const topRows = (hasMarketFutures ? data.market_futures : data.probabilities).slice(0, 8);
  const max = Math.max(
    ...topRows.map((row) => (hasMarketFutures ? row.implied_probability : row.champion)),
    0.01
  );
  els.championList.innerHTML = topRows
    .map(
      (row, index) => {
        const value = hasMarketFutures ? row.implied_probability : row.champion;
        const display = hasMarketFutures ? `${row.odds.toFixed(2)}倍` : pct(row.champion, 1);
        return `
        <div class="champion-row">
          <span>${index + 1}</span>
          <strong>${row.team}</strong>
          <i style="width:${Math.max(4, (value / max) * 100)}%"></i>
          <b>${display}</b>
        </div>
      `;
      }
    )
    .join("");
  els.championStatus.textContent = hasMarketFutures
    ? `冠军市场均赔 · ${topRows[0].bookmaker_count || 0} 家报价 · ${formatDateTime(topRows[0].updated_at)}`
    : `固定模型概率 · ${formatDateTime(data.generated_at)}`;
}

async function runTournament(seed = DEFAULT_TOURNAMENT_SEED) {
  els.championList.innerHTML = '<div class="loading">模拟中...</div>';
  els.championStatus.textContent = "正在读取固定冠军榜...";
  const params = new URLSearchParams({
    runs: "1200",
    seed: String(seed),
  });
  const data = await fetchJson(`/api/tournament?${params.toString()}`);
  renderChampions(data);
}

els.filters.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  state.filter = button.dataset.filter;
  els.filters.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
  renderTimeline();
});

els.rerunTournament.addEventListener("click", () => {
  runTournament(DEFAULT_TOURNAMENT_SEED).catch((error) => {
    els.championList.innerHTML = `<div class="loading">${error.message}</div>`;
    els.championStatus.textContent = "读取失败";
  });
});

Promise.all([loadTimeline(), runTournament()]).catch((error) => {
  els.timeline.innerHTML = `<div class="loading">${error.message}</div>`;
});
