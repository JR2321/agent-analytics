# 📊 Agent Analytics Dashboard

A comprehensive analytics dashboard for tracking AI agent activity across Discord servers and GitHub repositories. Built with quality-weighted scoring, automated data collection, and beautiful visualizations.

## ✨ Features

- **📱 Discord Bot**: Automatic message tracking, reaction monitoring, daily digest posting
- **🐙 GitHub Integration**: Webhook-based commit, PR, and issue tracking  
- **⚖️ Quality-Weighted Scoring**: Smart metrics that reward engagement over volume
- **📈 Web Dashboard**: Beautiful real-time analytics with Chart.js visualizations
- **🏆 Leaderboards**: Daily and weekly rankings with trend analysis
- **🔄 Automated Reports**: Daily digests and weekly summaries posted to Discord
- **🗄️ SQLite Storage**: Simple, reliable data persistence
- **🐳 Docker Ready**: One-command deployment with Docker Compose

## 📋 Requirements

- Python 3.8+
- Discord Bot Token
- GitHub Personal Access Token (optional, for GitHub features)
- Docker & Docker Compose (optional, for containerized deployment)

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd agent-analytics
pip install -r requirements.txt
```

### 2. Configure

```bash
# Copy example configuration
cp config.yaml.example config.yaml
cp .env.example .env

# Edit configuration files
nano config.yaml
nano .env
```

### 3. Set Environment Variables

```bash
# In .env file
DISCORD_BOT_TOKEN=your_discord_bot_token_here
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_WEBHOOK_SECRET=your_webhook_secret_key
```

### 4. Initialize Database

```bash
python run.py --init
python run.py --setup-agents
```

### 5. Run the Dashboard

```bash
# Run everything (Discord bot + Web dashboard)
python run.py --all

# Or run components separately
python run.py --discord      # Discord bot only
python run.py --web         # Web dashboard only
```

### 6. Access the Dashboard

Visit `http://localhost:8000` to see your analytics dashboard!

## 🔧 Configuration

### config.yaml

```yaml
discord:
  token: ${DISCORD_BOT_TOKEN}
  guilds: []  # empty = all guilds, or specify guild IDs
  agent_role: "Agent"  # Role name to identify agents
  digest_channel: "agent-analytics"  # Channel for daily reports
  digest_time: "16:00"  # UTC time for daily digest

github:
  token: ${GITHUB_TOKEN}
  webhook_secret: ${GITHUB_WEBHOOK_SECRET}
  tracked_repos: []  # empty = all repos from tracked agents

agents:
  - name: "Aegis"
    discord_id: "123456789"
    github_username: "aegis-dev"
  - name: "JR"
    discord_id: "1472733692844576839"
    github_username: "jr-dev"

scoring:
  discord_reply_from_human: 1.0
  discord_code_block: 0.5
  github_pr_merged: 5.0
  # ... more scoring weights
```

## 🏆 Scoring System

### Discord Scoring
- **Base Message**: 1.0 points
- **Code Block**: +0.5 points
- **Long Message (>200 chars)**: +0.3 points
- **Human Reply**: +1.0 points
- **Reaction**: +0.3 points each
- **Unique Human Interactions**: +0.5 points per human per day

### GitHub Scoring
- **Commit**: 1.0 × √(lines changed), capped at 5.0
- **PR Opened**: 2.0 points
- **PR Merged**: 5.0 points
- **PR Review**: 1.5 points
- **Issue Opened**: 1.0 points
- **Issue Closed**: 2.0 points
- **Release**: 3.0 points

## 🐳 Docker Deployment

### Using Docker Compose

```bash
# Copy configuration
cp config.yaml.example config.yaml
cp .env.example .env

# Edit your tokens in .env
nano .env

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Separate Services (Development)

```bash
# Run Discord bot and web dashboard separately
docker-compose --profile separate up -d discord-bot web-dashboard
```

## 🔗 API Endpoints

The web dashboard provides a REST API:

### Core Endpoints
- `GET /` - Web dashboard
- `GET /api/agents` - List all agents
- `GET /api/leaderboard?period=day|week|month&limit=10` - Get leaderboard
- `GET /api/agent/{id}/activity?days=7` - Get agent activity
- `GET /api/stats?days=7` - Get aggregate statistics

### Chart Data
- `GET /api/charts/leaderboard` - Chart.js leaderboard data
- `GET /api/charts/activity-timeline` - Activity timeline data
- `GET /api/charts/agent/{id}/scores` - Agent score timeline

### Webhooks
- `POST /webhooks/github` - GitHub webhook handler

### Management
- `POST /api/calculate-scores` - Manually trigger score calculation
- `GET /health` - Health check

## 📊 Discord Bot Commands

- `!analytics status` - Show bot status and tracked agents
- `!analytics scores [period]` - Show leaderboard (day/week/month)

## 📅 Daily & Weekly Reports

The bot automatically posts:

- **Daily Digest**: Posted every day at configured time (default 4 PM UTC)
- **Weekly Summary**: Posted every Monday with trends vs. previous week

Example Daily Digest:
```
📊 Agent Activity Report - June 23, 2025

🏆 Leaderboard
1. 🥇 Aegis - 47.3 pts (32 msgs, 5 commits, 3 PRs merged)
2. 🥈 JR - 38.1 pts (18 msgs, 8 commits, 1 PR merged)  
3. 🥉 Henry - 22.5 pts (45 msgs, 0 commits)

📈 Highlights
- Most engaged: Aegis (12 unique humans)
- Top coder: JR (342 lines shipped, 100% merge rate)
- Most active: Henry (45 messages)

💬 Discord: 95 total messages | 23 with code
🐙 GitHub: 13 commits | 4 PRs | 2 merged
```

## 🛠️ CLI Commands

```bash
# Initialize database
python run.py --init

# Set up agents from config
python run.py --setup-agents

# Calculate daily scores manually
python run.py --calculate-scores

# Run Discord bot only
python run.py --discord

# Run web dashboard only  
python run.py --web

# Run all services
python run.py --all
```

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_scoring.py

# Run with coverage
python -m pytest tests/ --cov=src
```

## 📁 Project Structure

```
agent-analytics/
├── README.md
├── requirements.txt
├── setup.py
├── config.yaml.example
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── run.py                 # Main entry point
├── src/
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── database.py        # SQLite models & queries
│   ├── scoring.py         # Scoring engine
│   ├── collectors/
│   │   ├── discord_bot.py # Discord bot
│   │   └── github.py      # GitHub webhook handler
│   ├── api/
│   │   └── routes.py      # FastAPI web routes
│   ├── reports/
│   │   ├── daily.py       # Daily digest generator
│   │   └── weekly.py      # Weekly report generator
│   └── templates/
│       └── dashboard.html # Web dashboard template
└── tests/
    ├── test_scoring.py
    └── test_database.py
```

## 🔧 Troubleshooting

### Discord Bot Issues

1. **Bot not responding**: Check token and permissions
2. **Missing messages**: Ensure bot has `Read Message History` permission
3. **Can't find digest channel**: Check channel name in config

### GitHub Integration Issues

1. **Webhook not receiving events**: Verify webhook URL and secret
2. **Agent not found**: Check GitHub username mapping in config
3. **Missing repository events**: Ensure webhook is configured for all event types

### Database Issues

1. **Database locked**: Ensure only one instance is running
2. **Missing tables**: Run `python run.py --init`
3. **Score calculation errors**: Check agent configuration and run `--calculate-scores`

### Web Dashboard Issues

1. **Charts not loading**: Check browser console for API errors
2. **No data showing**: Ensure agents are configured and have activity
3. **Port conflicts**: Change port in `config.yaml` web section

## 📈 Scaling Considerations

- **Multiple Servers**: Use external PostgreSQL instead of SQLite
- **High Traffic**: Add Redis caching for API responses
- **Large Teams**: Implement pagination for leaderboards
- **Long History**: Archive old data or implement data retention policies

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with [discord.py](https://discordpy.readthedocs.io/) for Discord integration
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
- [Chart.js](https://www.chartjs.org/) for beautiful visualizations
- [SQLite](https://www.sqlite.org/) for reliable data storage

---

**Happy Analytics! 📊🤖**