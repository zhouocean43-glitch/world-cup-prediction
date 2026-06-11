# World Cup Prediction Website

一个本地可打开的世界杯预测网站。当前版本无外部依赖，包含网页端、预测 API、赔率/新闻信号、比分模型和赛事模拟。

## 运行

```bash
python3 -m backend.server --port 8787
```

打开：

```text
http://127.0.0.1:8787
```

API 说明：

```text
http://127.0.0.1:8787/api
```

## 公网部署

这个项目不是纯静态页，赔率、冠军榜和时间轴都通过 Python 后端生成。GitHub Pages 只能托管静态文件，不能直接跑这个后端；如果希望别人打开一个公网 URL，推荐把本仓库接到 Render、Railway、Fly.io 或 VPS。

### Render 部署

仓库里已包含 `render.yaml`，上传到 GitHub 后可以在 Render 里用 Blueprint/Web Service 部署：

1. 在 Render 创建 Web Service，连接这个 GitHub 仓库。
2. Start Command 使用仓库里的配置：`python3 -m backend.server --host 0.0.0.0 --port $PORT`。
3. 在 Render 环境变量里设置 `ODDS_API_KEY`，不要把真实 key 写进仓库。
4. 保留或按需修改：

```text
ODDS_API_BOOKMAKERS=draftkings,fanduel,betmgm,bet365,pinnacle,betfair
ODDS_API_SPORT_KEYS=soccer_fifa_world_cup
ODDS_API_OUTRIGHT_SPORT_KEY=soccer_fifa_world_cup_winner
```

部署完成后，Render 会给一个公开访问地址。别人打开那个地址就能看同一个网站。

## API

- `GET /api/health`
- `GET /api/teams`
- `GET /api/groups`
- `GET /api/fixtures`
- `GET /api/timeline`
- `GET /api/predict?team_a=Argentina&team_b=Spain`
- `GET /api/tournament?runs=2000&seed=42`
- `GET /api/tournament?runs=2000&seed=42&refresh=1`
- `POST /api/predict`

`POST /api/predict` 示例：

```json
{
  "team_a": "Argentina",
  "team_b": "Spain",
  "market_odds": {
    "team_a": 2.35,
    "draw": 3.20,
    "team_b": 3.05
  },
  "market_weight": 0.25,
  "news": {
    "team_a_absences": 0,
    "team_b_absences": 1,
    "team_a_rest_days": 5,
    "team_b_rest_days": 4,
    "team_a_motivation": 0.6,
    "team_b_motivation": 0.5
  }
}
```

## 当前模型

- Elo-like 强度模型
- Poisson 比分分布模型
- 可选博彩公司赔率校准
- 可选新闻信号修正
- 48 队世界杯 Monte Carlo 模拟
- 冠军概率后端持久缓存，页面刷新不会抖动
- 小组赛时间轴自动预测
- 官方 A-L 分组种子
- 国旗、球场、地点、天气字段
- 第一场 Mexico vs South Africa 接入博彩公司赔率快照
- 球队总身价估算

## 每日信号更新

当前先使用本地 fallback provider 生成 `data/live_signals.json`：

```bash
python3 scripts/update_daily_signals.py
```

后续接入真实赔率和新闻源时，替换这个脚本里的 provider 即可，前端和 `/api/timeline` 不需要改。

### 接入主要博彩公司赔率

后端已接入 The Odds API 聚合通道。网页请求 `/api/timeline` 时会优先拉实时博彩公司均值；每日脚本可作为落盘备份：

```bash
export ODDS_API_KEY="你的 key"
python3 scripts/update_daily_signals.py
```

也可以在项目根目录创建 `.env`：

```text
ODDS_API_KEY=你的 key
ODDS_API_BOOKMAKERS=draftkings,fanduel,betmgm,bet365,pinnacle,betfair
```

默认会尝试聚合这些主要盘口来源：

```text
DraftKings, FanDuel, BetMGM, BetRivers, William Hill / Caesars,
Bet365, Pinnacle, Betfair, Unibet, Bovada
```

可选配置：

```bash
export ODDS_API_REGIONS="us,uk,eu"
export ODDS_API_BOOKMAKERS="draftkings,fanduel,betmgm,bet365,pinnacle,betfair"
export ODDS_API_SPORT_KEYS="soccer_fifa_world_cup"
export ODDS_API_OUTRIGHT_SPORT_KEY="soccer_fifa_world_cup_winner"
```

没有 `ODDS_API_KEY` 时，系统只显示首场 FOX Sports 快照和模型占位线，不再生成随机盘口波动。

## 数据可信度

- 第一场：Mexico vs South Africa，已接入已知赛程、球场、天气快照和 FOX Sports 赔率快照。
- 其它场次：分组和对阵使用官方抽签种子；详细球场/天气等待官方赛程 provider 导入后逐场补齐。
- 赔率：有 bookmaker snapshot 时用市场权重强融合；否则明确标记为 `model_placeholder`。
- 冠军榜：有 outright 市场时显示博彩公司冠军均赔；否则显示固定缓存的模型冠军概率。
- 身价：当前为本地估算字段，后续可替换为 Transfermarkt/FotMob 等数据源。

## 说明

`backend/data.py` 里的球队和小组是 demo seed，不声称是官方赛程。正式接入时应替换为官方分组、赛程、赔率和新闻 provider。

## 测试

```bash
python3 -m unittest discover -s tests
```
