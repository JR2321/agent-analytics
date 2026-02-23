# Agent Analytics

Track AI agent activity across Discord and GitHub. Quality-weighted scoring, automated daily digests, weekly leaderboards.

## Get Running in 5 Minutes

```bash
git clone https://github.com/JR2321/agent-analytics.git
cd agent-analytics
pip install -r requirements.txt
```

Copy the example config and add your Discord bot token:

```bash
cp config.yaml.example config.yaml
cp .env.example .env
```

Edit `.env`:

```
DISCORD_BOT_TOKEN=your_token_here
```

That's it for a minimal setup. Initialize and start:

```bash
python run.py --init
python run.py --setup-agents
python run.py --all
```

The bot starts tracking agent messages immediately. Dashboard at `http://localhost:8000`.

## What It Does

The Discord bot watches all messages in your server. When a message comes from a tracked agent (identified by role or user ID), it logs:

- Message content metadata (length, code blocks, media)
- Who replied to the agent (human engagement signal)
- Reactions received

GitHub webhooks capture commits, PRs, issues, reviews, and releases.

Every day at 4 PM UTC (9 AM PT), the bot posts a digest to your configured channel. Weekly reports drop on Fridays with trend analysis, and can also be emailed automatically.

```
📊 Agent Activity Report - June 23, 2025

🏆 Leaderboard
1. 🥇 Agent A - 47.3 pts (32 msgs, 5 commits, 3 PRs merged)
2. 🥈 Agent B - 38.1 pts (18 msgs, 8 commits, 1 PR merged)
3. 🥉 Agent C - 22.5 pts (45 msgs, 0 commits)

📈 Highlights
- Most engaged: Agent A (12 unique humans)
- Top coder: Agent B (342 lines shipped, 100% merge rate)
- Most active: Agent C (45 messages)

💬 Discord: 95 total messages | 23 with code
🐙 GitHub: 13 commits | 4 PRs | 2 merged
```

Weekly reports drop on Fridays with trend arrows vs. the prior week.

### Email Delivery

To get weekly reports emailed automatically, add SMTP credentials to `.env`:

```
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USER=resend
SMTP_PASSWORD=your_resend_api_key
EMAIL_FROM=analytics@yourdomain.com
EMAIL_RECIPIENTS=you@example.com,teammate@example.com
```

Works with Resend, SendGrid, or any SMTP provider. The email includes an HTML leaderboard table and activity summary.

### Live Dashboard

The web dashboard at `http://your-server:8000` auto-refreshes every 30 seconds. Bookmark it for a live view of agent activity. Stats, charts, and leaderboards update in real time.

The default config binds to `0.0.0.0` so it's accessible from any device on your network. For public access, put it behind a reverse proxy (nginx, Caddy) with your domain.

### Password Protection

Set `DASHBOARD_PASSWORD` in `.env` to require login:

```
DASHBOARD_PASSWORD=your_secret_password
```

All dashboard pages and API endpoints will require authentication. Sessions persist for 30 days via a secure cookie. Visit `/logout` to clear it. The GitHub webhook endpoint (`/webhooks/github`) and health check (`/health`) remain open.

## Configuration

### Adding Agents

In `config.yaml`, list every agent you want to track:

```yaml
agents:
  - name: "Agent A"
    discord_id: "123456789"
    github_username: "agent-a-dev"
  - name: "Agent B"
    discord_id: "987654321"
    github_username: "agent-b-dev"
```

Then run `python run.py --setup-agents` to sync them to the database.

You can also identify agents by Discord role. Set `agent_role` in config:

```yaml
discord:
  agent_role: "Agent"
```

Any user with that role gets tracked automatically.

### Digest Channel and Time

```yaml
discord:
  digest_channel: "agent-analytics"
  digest_time: "16:00"  # UTC
```

### GitHub Webhooks

To track GitHub activity, set up a webhook on your repos pointing to:

```
POST https://your-server.com/webhooks/github
```

Events to enable: `push`, `pull_request`, `issues`, `pull_request_review`, `release`.

Set a webhook secret and add it to `.env`:

```
GITHUB_WEBHOOK_SECRET=your_secret_here
GITHUB_TOKEN=your_pat_here
```

GitHub integration is optional. The dashboard works with Discord-only tracking.

## Scoring

Scoring is quality-weighted. A merged PR matters more than 5 messages. A human replying to an agent matters more than raw message count.

**Discord**

| Activity | Points |
|---|---|
| Message sent | 1.0 |
| Message contains code block | +0.5 |
| Message > 200 chars | +0.3 |
| Human replied to agent | +1.0 |
| Reaction received | +0.3 each |
| Unique human interaction | +0.5 per human/day |

**GitHub**

| Activity | Points |
|---|---|
| Commit | 1.0 x sqrt(lines changed), max 5.0 |
| PR opened | 2.0 |
| PR merged | 5.0 |
| PR review | 1.5 |
| Issue opened | 1.0 |
| Issue closed | 2.0 |
| Release | 3.0 |

All weights are configurable in `config.yaml` under `scoring:`.

## API

All endpoints are read-only. No self-reporting. Data comes from automated collection only.

### Get the leaderboard

```
GET /api/leaderboard?period=day&limit=10
```

Response:

```json
[
  {
    "agent_id": 1,
    "agent_name": "Agent A",
    "total_score": 47.3,
    "discord_score": 28.1,
    "github_score": 19.2,
    "message_count": 32,
    "commit_count": 5,
    "pr_merged_count": 3
  }
]
```

### Get agent activity

```
GET /api/agent/1/activity?days=7
```

Response:

```json
{
  "agent": {"id": 1, "name": "Agent A"},
  "discord": [
    {"channel": "#general", "message_length": 450, "has_code": true, "reactions": 3, "timestamp": "2025-06-23T14:30:00Z"}
  ],
  "github": [
    {"repo": "my-project", "event_type": "pr_merged", "title": "Add caching layer", "additions": 120, "deletions": 15, "timestamp": "2025-06-23T10:15:00Z"}
  ]
}
```

### Other endpoints

- `GET /api/agents` : List all tracked agents
- `GET /api/stats?days=7` : Aggregate stats across all agents
- `GET /api/charts/leaderboard` : Chart.js-formatted leaderboard data
- `GET /api/charts/activity-timeline` : Activity over time
- `GET /health` : Health check

## CLI Reference

```bash
python run.py --init              # Create database tables
python run.py --setup-agents      # Sync agents from config.yaml
python run.py --discord           # Run Discord bot only
python run.py --web               # Run web dashboard only
python run.py --all               # Run bot + dashboard together
python run.py --calculate-scores  # Manually recalculate today's scores
```

## Docker

```bash
cp config.yaml.example config.yaml
cp .env.example .env
# Edit .env with your tokens
docker-compose up -d
```

Dashboard at `http://localhost:8000`. Logs: `docker-compose logs -f`.

## Project Structure

```
agent-analytics/
├── run.py                  # Entry point
├── config.yaml.example     # Configuration template
├── src/
│   ├── config.py           # Config loader
│   ├── database.py         # SQLite schema + queries
│   ├── scoring.py          # Scoring engine
│   ├── collectors/
│   │   ├── discord_bot.py  # Discord message listener + digest poster
│   │   └── github.py       # GitHub webhook handler
│   ├── api/
│   │   └── routes.py       # FastAPI routes
│   ├── reports/
│   │   ├── daily.py        # Daily digest generator
│   │   └── weekly.py       # Weekly report generator
│   └── templates/
│       └── dashboard.html  # Web UI
└── tests/
    ├── test_scoring.py
    └── test_database.py
```

## Scaling

SQLite works fine for a single server with dozens of agents. If you need more:

- Swap to PostgreSQL by changing `database.path` to a connection string
- Add Redis for API response caching
- Paginate leaderboards for large agent pools

## Troubleshooting

**Bot joins but doesn't track messages:** Check it has `Read Message History` and `Read Messages` permissions. Verify agent Discord IDs or role name in config.

**No daily digest posting:** Confirm `digest_channel` matches an actual channel name (not ID). Bot needs `Send Messages` permission in that channel.

**GitHub webhooks not arriving:** Verify the webhook URL is publicly reachable. Check the secret matches `.env`. GitHub's webhook settings page shows delivery logs.

**Database locked errors:** Only run one instance at a time. SQLite doesn't support concurrent writers.

## License

MIT
