"""Configuration management for agent analytics dashboard."""
import os
import yaml
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiscordConfig:
    token: str
    guilds: List[int] = field(default_factory=list)
    agent_role: str = "Agent"
    agent_ids: List[int] = field(default_factory=list)
    digest_channel: str = "agent-analytics"
    digest_time: str = "16:00"  # UTC


@dataclass
class GitHubConfig:
    token: str
    webhook_secret: str
    tracked_repos: List[str] = field(default_factory=list)


@dataclass
class AgentConfig:
    name: str
    discord_id: Optional[str] = None
    github_username: Optional[str] = None


@dataclass
class ScoringConfig:
    discord_reply_from_human: float = 1.0
    discord_code_block: float = 0.5
    discord_long_message: float = 0.3
    discord_reaction: float = 0.3
    discord_unique_human: float = 0.5
    github_commit_base: float = 1.0
    github_commit_max: float = 5.0
    github_pr_opened: float = 2.0
    github_pr_merged: float = 5.0
    github_pr_review: float = 1.5
    github_issue_opened: float = 1.0
    github_issue_closed: float = 2.0
    github_release: float = 3.0


@dataclass
class DatabaseConfig:
    path: str = "data/analytics.db"


@dataclass
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8000


@dataclass
class Config:
    discord: DiscordConfig
    github: GitHubConfig
    agents: List[AgentConfig]
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    web: WebConfig = field(default_factory=WebConfig)


def expand_env_vars(data: Any) -> Any:
    """Recursively expand environment variables in config data."""
    if isinstance(data, dict):
        return {k: expand_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars(item) for item in data]
    elif isinstance(data, str):
        return os.path.expandvars(data)
    return data


def load_config(config_path: str = "config.yaml") -> Config:
    """Load configuration from YAML file with environment variable expansion."""
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_file, 'r') as f:
        raw_config = yaml.safe_load(f)
    
    # Expand environment variables
    expanded_config = expand_env_vars(raw_config)
    
    # Parse Discord config
    discord_data = expanded_config.get('discord', {})
    discord_config = DiscordConfig(
        token=discord_data['token'],
        guilds=discord_data.get('guilds', []),
        agent_role=discord_data.get('agent_role', 'Agent'),
        agent_ids=discord_data.get('agent_ids', []),
        digest_channel=discord_data.get('digest_channel', 'agent-analytics'),
        digest_time=discord_data.get('digest_time', '16:00')
    )
    
    # Parse GitHub config
    github_data = expanded_config.get('github', {})
    github_config = GitHubConfig(
        token=github_data['token'],
        webhook_secret=github_data['webhook_secret'],
        tracked_repos=github_data.get('tracked_repos', [])
    )
    
    # Parse agents
    agents_data = expanded_config.get('agents', [])
    agents = [
        AgentConfig(
            name=agent['name'],
            discord_id=agent.get('discord_id'),
            github_username=agent.get('github_username')
        )
        for agent in agents_data
    ]
    
    # Parse scoring config
    scoring_data = expanded_config.get('scoring', {})
    scoring_config = ScoringConfig(**scoring_data)
    
    # Parse database config
    db_data = expanded_config.get('database', {})
    database_config = DatabaseConfig(**db_data)
    
    # Parse web config
    web_data = expanded_config.get('web', {})
    web_config = WebConfig(**web_data)
    
    return Config(
        discord=discord_config,
        github=github_config,
        agents=agents,
        scoring=scoring_config,
        database=database_config,
        web=web_config
    )


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration instance."""
    global _config
    _config = config