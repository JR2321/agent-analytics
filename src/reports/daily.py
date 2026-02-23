"""Daily report generator for Discord digests."""
from datetime import date, datetime, timedelta
from typing import Dict, List, Any
import discord
import aiosqlite

from ..database import get_db
from ..config import get_config


class DailyReportGenerator:
    """Generates daily activity reports as Discord embeds."""
    
    def __init__(self):
        self.db = None
    
    async def init(self):
        """Initialize the report generator."""
        if self.db is None:
            self.db = await get_db()
    
    async def generate_embed(self, target_date: date = None) -> discord.Embed:
        """Generate daily report embed."""
        await self.init()
        
        if target_date is None:
            target_date = date.today() - timedelta(days=1)  # Default to yesterday
        
        # Get leaderboard for the day
        leaderboard = await self.db.get_leaderboard(period="day", limit=10)
        
        # Get activity stats
        activity_stats = await self.db.get_activity_stats(days=1)
        
        # Get additional metrics
        metrics = await self._get_daily_metrics(target_date)
        
        # Create embed
        embed = discord.Embed(
            title=f"📊 Agent Activity Report - {target_date.strftime('%B %d, %Y')}",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        # Leaderboard section
        if leaderboard:
            leaderboard_text = []
            for i, agent in enumerate(leaderboard[:5], 1):  # Top 5
                emoji = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
                
                name = agent['name']
                total_score = agent.get('total_score', 0) or 0
                discord_score = agent.get('discord_score', 0) or 0
                github_score = agent.get('github_score', 0) or 0
                
                # Get message and commit counts for this agent
                agent_metrics = await self._get_agent_daily_metrics(
                    agent['name'], target_date
                )
                
                msg_count = agent_metrics.get('messages', 0)
                commit_count = agent_metrics.get('commits', 0)
                pr_count = agent_metrics.get('prs_merged', 0)
                
                detail_parts = []
                if msg_count > 0:
                    detail_parts.append(f"{msg_count} msgs")
                if commit_count > 0:
                    detail_parts.append(f"{commit_count} commits")
                if pr_count > 0:
                    detail_parts.append(f"{pr_count} PRs merged")
                
                detail = f"({', '.join(detail_parts)})" if detail_parts else ""
                
                leaderboard_text.append(
                    f"{emoji} {name} - {total_score:.1f} pts {detail}"
                )
            
            embed.add_field(
                name="🏆 Leaderboard",
                value="\n".join(leaderboard_text) if leaderboard_text else "No activity",
                inline=False
            )
        
        # Highlights section
        highlights = await self._generate_highlights(target_date, leaderboard)
        if highlights:
            embed.add_field(
                name="📈 Highlights",
                value="\n".join(highlights),
                inline=False
            )
        
        # Activity summary
        discord_stats = activity_stats.get('discord', {})
        github_stats = activity_stats.get('github', {})
        
        discord_summary = (
            f"💬 Discord: {discord_stats.get('total_messages', 0)} total messages"
            f" | {discord_stats.get('messages_with_code', 0)} with code"
        )
        
        github_summary = (
            f"🐙 GitHub: {github_stats.get('commits', 0)} commits"
            f" | {github_stats.get('prs', 0)} PRs"
            f" | {github_stats.get('merged_prs', 0)} merged"
        )
        
        embed.add_field(
            name="📊 Activity Summary",
            value=f"{discord_summary}\n{github_summary}",
            inline=False
        )
        
        # Footer
        embed.set_footer(
            text="Agent Analytics Dashboard • Daily Digest",
            icon_url="https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"
        )
        
        return embed
    
    async def _get_daily_metrics(self, target_date: date) -> Dict[str, Any]:
        """Get aggregated daily metrics."""
        start_time = datetime.combine(target_date, datetime.min.time())
        end_time = start_time + timedelta(days=1)
        
        async with aiosqlite.connect(self.db.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Discord metrics
            cursor = await db.execute("""
                SELECT 
                    COUNT(*) as total_messages,
                    COUNT(CASE WHEN has_code THEN 1 END) as messages_with_code,
                    COUNT(CASE WHEN reply_to_human THEN 1 END) as replies_to_humans,
                    SUM(reactions_received) as total_reactions,
                    COUNT(DISTINCT agent_id) as active_agents_discord
                FROM discord_activity
                WHERE timestamp >= ? AND timestamp < ?
            """, (start_time, end_time))
            discord_metrics = dict(await cursor.fetchone())
            
            # GitHub metrics
            cursor = await db.execute("""
                SELECT 
                    COUNT(*) as total_events,
                    COUNT(CASE WHEN event_type = 'commit' THEN 1 END) as commits,
                    COUNT(CASE WHEN event_type = 'pull_request' THEN 1 END) as prs,
                    COUNT(CASE WHEN event_type = 'pull_request' AND was_merged THEN 1 END) as merged_prs,
                    COUNT(CASE WHEN event_type = 'release' THEN 1 END) as releases,
                    COUNT(DISTINCT agent_id) as active_agents_github
                FROM github_activity
                WHERE timestamp >= ? AND timestamp < ?
            """, (start_time, end_time))
            github_metrics = dict(await cursor.fetchone())
            
            return {
                "discord": discord_metrics,
                "github": github_metrics
            }
    
    async def _get_agent_daily_metrics(self, agent_name: str, target_date: date) -> Dict[str, Any]:
        """Get daily metrics for a specific agent."""
        start_time = datetime.combine(target_date, datetime.min.time())
        end_time = start_time + timedelta(days=1)
        
        async with aiosqlite.connect(self.db.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Get agent ID
            cursor = await db.execute("SELECT id FROM agents WHERE name = ?", (agent_name,))
            agent_row = await cursor.fetchone()
            if not agent_row:
                return {}
            
            agent_id = agent_row['id']
            
            # Discord metrics
            cursor = await db.execute("""
                SELECT COUNT(*) as messages
                FROM discord_activity
                WHERE agent_id = ? AND timestamp >= ? AND timestamp < ?
            """, (agent_id, start_time, end_time))
            discord_result = await cursor.fetchone()
            messages = discord_result['messages'] if discord_result else 0
            
            # GitHub metrics
            cursor = await db.execute("""
                SELECT 
                    COUNT(CASE WHEN event_type = 'commit' THEN 1 END) as commits,
                    COUNT(CASE WHEN event_type = 'pull_request' AND was_merged THEN 1 END) as prs_merged
                FROM github_activity
                WHERE agent_id = ? AND timestamp >= ? AND timestamp < ?
            """, (agent_id, start_time, end_time))
            github_result = await cursor.fetchone()
            
            return {
                "messages": messages,
                "commits": github_result['commits'] if github_result else 0,
                "prs_merged": github_result['prs_merged'] if github_result else 0
            }
    
    async def _generate_highlights(self, target_date: date, leaderboard: List[Dict[str, Any]]) -> List[str]:
        """Generate daily highlights."""
        highlights = []
        
        if not leaderboard:
            return highlights
        
        # Most engaged (highest Discord score)
        top_discord = max(leaderboard, key=lambda x: x.get('discord_score', 0) or 0)
        if top_discord.get('discord_score', 0) > 0:
            highlights.append(f"- Most engaged: {top_discord['name']} (Discord activity)")
        
        # Top coder (highest GitHub score)
        top_github = max(leaderboard, key=lambda x: x.get('github_score', 0) or 0)
        if top_github.get('github_score', 0) > 0:
            agent_metrics = await self._get_agent_daily_metrics(top_github['name'], target_date)
            commits = agent_metrics.get('commits', 0)
            prs = agent_metrics.get('prs_merged', 0)
            
            detail_parts = []
            if commits > 0:
                detail_parts.append(f"{commits} commits")
            if prs > 0:
                detail_parts.append(f"{prs} PRs merged")
            
            detail = f" ({', '.join(detail_parts)})" if detail_parts else ""
            highlights.append(f"- Top coder: {top_github['name']}{detail}")
        
        # Most active (by message count)
        most_active = None
        max_messages = 0
        
        for agent in leaderboard:
            agent_metrics = await self._get_agent_daily_metrics(agent['name'], target_date)
            messages = agent_metrics.get('messages', 0)
            if messages > max_messages:
                max_messages = messages
                most_active = agent
        
        if most_active and max_messages > 0:
            highlights.append(f"- Most active: {most_active['name']} ({max_messages} messages)")
        
        return highlights[:3]  # Limit to top 3 highlights