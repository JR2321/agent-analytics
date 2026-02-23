"""Database models and queries for agent analytics."""
import aiosqlite
import json
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from .config import get_config


class Database:
    """Async SQLite database wrapper for agent analytics."""
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            config = get_config()
            db_path = config.database.path
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def init_db(self):
        """Initialize database with required tables."""
        async with aiosqlite.connect(self.db_path) as db:
            # Agents table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    discord_id TEXT,
                    github_username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Discord activity table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS discord_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id INTEGER NOT NULL,
                    channel_id TEXT NOT NULL,
                    channel_name TEXT,
                    guild_id TEXT NOT NULL,
                    message_id TEXT NOT NULL UNIQUE,
                    message_length INTEGER NOT NULL DEFAULT 0,
                    has_code BOOLEAN DEFAULT FALSE,
                    has_media BOOLEAN DEFAULT FALSE,
                    reply_to_agent BOOLEAN DEFAULT FALSE,
                    reply_to_human BOOLEAN DEFAULT FALSE,
                    reactions_received INTEGER DEFAULT 0,
                    timestamp TIMESTAMP NOT NULL,
                    FOREIGN KEY (agent_id) REFERENCES agents (id)
                )
            """)
            
            # GitHub activity table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS github_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id INTEGER NOT NULL,
                    repo TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    title TEXT,
                    additions INTEGER DEFAULT 0,
                    deletions INTEGER DEFAULT 0,
                    files_changed INTEGER DEFAULT 0,
                    was_merged BOOLEAN DEFAULT FALSE,
                    timestamp TIMESTAMP NOT NULL,
                    FOREIGN KEY (agent_id) REFERENCES agents (id)
                )
            """)
            
            # Daily scores table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS daily_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    discord_score REAL NOT NULL DEFAULT 0.0,
                    github_score REAL NOT NULL DEFAULT 0.0,
                    total_score REAL NOT NULL DEFAULT 0.0,
                    metrics_json TEXT,
                    UNIQUE(agent_id, date),
                    FOREIGN KEY (agent_id) REFERENCES agents (id)
                )
            """)
            
            # Create indexes for better performance
            await db.execute("CREATE INDEX IF NOT EXISTS idx_discord_activity_agent_timestamp ON discord_activity (agent_id, timestamp)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_github_activity_agent_timestamp ON github_activity (agent_id, timestamp)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_daily_scores_date ON daily_scores (date)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_agents_discord_id ON agents (discord_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_agents_github_username ON agents (github_username)")
            
            await db.commit()
    
    async def upsert_agent(self, name: str, discord_id: Optional[str] = None, github_username: Optional[str] = None) -> int:
        """Insert or update an agent record."""
        async with aiosqlite.connect(self.db_path) as db:
            # Try to update existing agent first
            await db.execute("""
                UPDATE agents 
                SET discord_id = COALESCE(?, discord_id),
                    github_username = COALESCE(?, github_username)
                WHERE name = ?
            """, (discord_id, github_username, name))
            
            if db.total_changes == 0:
                # Insert new agent if update didn't affect any rows
                await db.execute("""
                    INSERT INTO agents (name, discord_id, github_username)
                    VALUES (?, ?, ?)
                """, (name, discord_id, github_username))
            
            # Get the agent ID
            cursor = await db.execute("SELECT id FROM agents WHERE name = ?", (name,))
            result = await cursor.fetchone()
            await db.commit()
            return result[0] if result else None
    
    async def get_agent_by_discord_id(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Get agent by Discord ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM agents WHERE discord_id = ?", (discord_id,))
            result = await cursor.fetchone()
            return dict(result) if result else None
    
    async def get_agent_by_github_username(self, github_username: str) -> Optional[Dict[str, Any]]:
        """Get agent by GitHub username."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM agents WHERE github_username = ?", (github_username,))
            result = await cursor.fetchone()
            return dict(result) if result else None
    
    async def add_discord_activity(self, agent_id: int, channel_id: str, channel_name: str, 
                                   guild_id: str, message_id: str, message_length: int,
                                   has_code: bool = False, has_media: bool = False,
                                   reply_to_agent: bool = False, reply_to_human: bool = False,
                                   reactions_received: int = 0, timestamp: datetime = None):
        """Add Discord activity record."""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO discord_activity 
                (agent_id, channel_id, channel_name, guild_id, message_id, message_length,
                 has_code, has_media, reply_to_agent, reply_to_human, reactions_received, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (agent_id, channel_id, channel_name, guild_id, message_id, message_length,
                  has_code, has_media, reply_to_agent, reply_to_human, reactions_received, timestamp))
            await db.commit()
    
    async def add_github_activity(self, agent_id: int, repo: str, event_type: str,
                                  title: str = None, additions: int = 0, deletions: int = 0,
                                  files_changed: int = 0, was_merged: bool = False,
                                  timestamp: datetime = None):
        """Add GitHub activity record."""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO github_activity 
                (agent_id, repo, event_type, title, additions, deletions, files_changed, was_merged, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (agent_id, repo, event_type, title, additions, deletions, files_changed, was_merged, timestamp))
            await db.commit()
    
    async def update_daily_scores(self, agent_id: int, date: date, discord_score: float,
                                  github_score: float, metrics: Dict[str, Any]):
        """Update daily scores for an agent."""
        total_score = discord_score + github_score
        metrics_json = json.dumps(metrics)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO daily_scores
                (agent_id, date, discord_score, github_score, total_score, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (agent_id, date, discord_score, github_score, total_score, metrics_json))
            await db.commit()
    
    async def get_agents(self) -> List[Dict[str, Any]]:
        """Get all agents."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM agents ORDER BY name")
            results = await cursor.fetchall()
            return [dict(row) for row in results]
    
    async def get_leaderboard(self, period: str = "day", limit: int = 10) -> List[Dict[str, Any]]:
        """Get leaderboard for specified period."""
        if period == "day":
            date_filter = "date = date('now')"
        elif period == "week":
            date_filter = "date >= date('now', '-7 days')"
        elif period == "month":
            date_filter = "date >= date('now', '-30 days')"
        else:
            raise ValueError(f"Invalid period: {period}")
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(f"""
                SELECT a.name, a.discord_id, a.github_username,
                       SUM(ds.discord_score) as discord_score,
                       SUM(ds.github_score) as github_score,
                       SUM(ds.total_score) as total_score
                FROM agents a
                LEFT JOIN daily_scores ds ON a.id = ds.agent_id
                WHERE {date_filter}
                GROUP BY a.id
                ORDER BY total_score DESC
                LIMIT ?
            """, (limit,))
            results = await cursor.fetchall()
            return [dict(row) for row in results]
    
    async def get_agent_activity(self, agent_id: int, days: int = 7) -> Dict[str, Any]:
        """Get detailed activity for an agent over specified days."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Get Discord activity
            cursor = await db.execute("""
                SELECT * FROM discord_activity
                WHERE agent_id = ? AND timestamp >= datetime('now', '-{} days')
                ORDER BY timestamp DESC
            """.format(days), (agent_id,))
            discord_activity = [dict(row) for row in await cursor.fetchall()]
            
            # Get GitHub activity
            cursor = await db.execute("""
                SELECT * FROM github_activity
                WHERE agent_id = ? AND timestamp >= datetime('now', '-{} days')
                ORDER BY timestamp DESC
            """.format(days), (agent_id,))
            github_activity = [dict(row) for row in await cursor.fetchall()]
            
            # Get daily scores
            cursor = await db.execute("""
                SELECT * FROM daily_scores
                WHERE agent_id = ? AND date >= date('now', '-{} days')
                ORDER BY date DESC
            """.format(days), (agent_id,))
            daily_scores = [dict(row) for row in await cursor.fetchall()]
            
            return {
                "discord_activity": discord_activity,
                "github_activity": github_activity,
                "daily_scores": daily_scores
            }
    
    async def get_activity_stats(self, days: int = 1) -> Dict[str, Any]:
        """Get aggregate activity stats."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Discord stats
            cursor = await db.execute(f"""
                SELECT 
                    COUNT(*) as total_messages,
                    COUNT(CASE WHEN has_code THEN 1 END) as messages_with_code,
                    SUM(reactions_received) as total_reactions
                FROM discord_activity
                WHERE timestamp >= datetime('now', '-{days} days')
            """)
            discord_stats = dict(await cursor.fetchone())
            
            # GitHub stats  
            cursor = await db.execute(f"""
                SELECT 
                    COUNT(*) as total_events,
                    COUNT(CASE WHEN event_type = 'commit' THEN 1 END) as commits,
                    COUNT(CASE WHEN event_type = 'pull_request' THEN 1 END) as prs,
                    COUNT(CASE WHEN event_type = 'pull_request' AND was_merged THEN 1 END) as merged_prs
                FROM github_activity
                WHERE timestamp >= datetime('now', '-{days} days')
            """)
            github_stats = dict(await cursor.fetchone())
            
            return {
                "discord": discord_stats,
                "github": github_stats
            }


# Global database instance
_db: Optional[Database] = None


async def get_db() -> Database:
    """Get the global database instance."""
    global _db
    if _db is None:
        _db = Database()
        await _db.init_db()
    return _db