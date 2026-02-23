"""Weekly report generator for Discord digests."""
from datetime import date, datetime, timedelta
from typing import Dict, List, Any, Tuple
import discord
import aiosqlite

from ..database import get_db
from ..config import get_config


class WeeklyReportGenerator:
    """Generates weekly activity reports as Discord embeds."""
    
    def __init__(self):
        self.db = None
    
    async def init(self):
        """Initialize the report generator."""
        if self.db is None:
            self.db = await get_db()
    
    async def generate_embed(self, end_date: date = None) -> discord.Embed:
        """Generate weekly report embed."""
        await self.init()
        
        if end_date is None:
            end_date = date.today() - timedelta(days=1)  # Default to yesterday
        
        start_date = end_date - timedelta(days=6)  # 7-day period
        
        # Get leaderboard for the week
        leaderboard = await self.db.get_leaderboard(period="week", limit=10)
        
        # Get weekly activity stats
        activity_stats = await self.db.get_activity_stats(days=7)
        
        # Get trends (compare to previous week)
        trends = await self._get_weekly_trends(end_date)
        
        # Create embed
        embed = discord.Embed(
            title=f"📊 Weekly Agent Activity Report",
            description=f"{start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}",
            color=0x0066ff,
            timestamp=datetime.utcnow()
        )
        
        # Leaderboard section
        if leaderboard:
            leaderboard_text = []
            for i, agent in enumerate(leaderboard[:8], 1):  # Top 8 for weekly
                emoji = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
                
                name = agent['name']
                total_score = agent.get('total_score', 0) or 0
                
                # Get weekly metrics for this agent
                agent_metrics = await self._get_agent_weekly_metrics(
                    agent['name'], start_date, end_date
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
                    detail_parts.append(f"{pr_count} PRs")
                
                detail = f"({', '.join(detail_parts)})" if detail_parts else ""
                
                # Add trend indicator
                trend_emoji = ""
                agent_trend = trends.get(name, {})
                score_change = agent_trend.get('score_change', 0)
                if score_change > 5:
                    trend_emoji = "📈"
                elif score_change < -5:
                    trend_emoji = "📉"
                
                leaderboard_text.append(
                    f"{emoji} {name} - {total_score:.1f} pts {detail} {trend_emoji}"
                )
            
            embed.add_field(
                name="🏆 Weekly Leaderboard",
                value="\n".join(leaderboard_text) if leaderboard_text else "No activity",
                inline=False
            )
        
        # Weekly highlights
        highlights = await self._generate_weekly_highlights(start_date, end_date, leaderboard)
        if highlights:
            embed.add_field(
                name="🌟 Weekly Highlights",
                value="\n".join(highlights),
                inline=False
            )
        
        # Activity summary with trends
        discord_stats = activity_stats.get('discord', {})
        github_stats = activity_stats.get('github', {})
        
        discord_trend = trends.get('_totals', {}).get('discord_change', 0)
        github_trend = trends.get('_totals', {}).get('github_change', 0)
        
        discord_emoji = self._get_trend_emoji(discord_trend)
        github_emoji = self._get_trend_emoji(github_trend)
        
        discord_summary = (
            f"💬 Discord: {discord_stats.get('total_messages', 0)} messages"
            f" | {discord_stats.get('messages_with_code', 0)} with code {discord_emoji}"
        )
        
        github_summary = (
            f"🐙 GitHub: {github_stats.get('commits', 0)} commits"
            f" | {github_stats.get('prs', 0)} PRs"
            f" | {github_stats.get('merged_prs', 0)} merged {github_emoji}"
        )
        
        embed.add_field(
            name="📊 Weekly Activity",
            value=f"{discord_summary}\n{github_summary}",
            inline=False
        )
        
        # Top performers in different categories
        top_performers = await self._get_top_performers(start_date, end_date)
        if top_performers:
            performers_text = []
            for category, agent_name in top_performers.items():
                if agent_name:
                    performers_text.append(f"• {category}: {agent_name}")
            
            if performers_text:
                embed.add_field(
                    name="🎯 Top Performers",
                    value="\n".join(performers_text),
                    inline=False
                )
        
        # Footer
        embed.set_footer(
            text="Agent Analytics Dashboard • Weekly Summary",
            icon_url="https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png"
        )
        
        return embed
    
    def _get_trend_emoji(self, change: float) -> str:
        """Get trend emoji based on change value."""
        if change > 10:
            return "📈"
        elif change > 0:
            return "↗️"
        elif change < -10:
            return "📉"
        elif change < 0:
            return "↘️"
        return "➡️"
    
    async def _get_weekly_trends(self, end_date: date) -> Dict[str, Any]:
        """Get weekly trends compared to previous week."""
        this_week_start = end_date - timedelta(days=6)
        last_week_end = this_week_start - timedelta(days=1)
        last_week_start = last_week_end - timedelta(days=6)
        
        # Get this week's leaderboard
        this_week = await self.db.get_leaderboard(period="week", limit=20)
        
        # Get last week's scores by manually querying
        last_week_scores = await self._get_period_scores(last_week_start, last_week_end)
        
        trends = {}
        total_this_week = 0
        total_last_week = 0
        
        for agent in this_week:
            name = agent['name']
            this_score = agent.get('total_score', 0) or 0
            last_score = last_week_scores.get(name, 0)
            
            trends[name] = {
                'score_change': this_score - last_score,
                'this_week': this_score,
                'last_week': last_score
            }
            
            total_this_week += this_score
            if name in last_week_scores:
                total_last_week += last_score
        
        # Add total trends
        trends['_totals'] = {
            'score_change': total_this_week - total_last_week,
            'discord_change': 0,  # Could calculate separately
            'github_change': 0    # Could calculate separately
        }
        
        return trends
    
    async def _get_period_scores(self, start_date: date, end_date: date) -> Dict[str, float]:
        """Get total scores for a specific period."""
        scores = {}
        
        async with aiosqlite.connect(self.db.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute("""
                SELECT a.name, SUM(ds.total_score) as total_score
                FROM agents a
                LEFT JOIN daily_scores ds ON a.id = ds.agent_id
                WHERE ds.date >= ? AND ds.date <= ?
                GROUP BY a.id
            """, (start_date, end_date))
            
            results = await cursor.fetchall()
            for row in results:
                scores[row['name']] = row['total_score'] or 0
        
        return scores
    
    async def _get_agent_weekly_metrics(self, agent_name: str, start_date: date, end_date: date) -> Dict[str, Any]:
        """Get weekly metrics for a specific agent."""
        start_time = datetime.combine(start_date, datetime.min.time())
        end_time = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        
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
    
    async def _generate_weekly_highlights(self, start_date: date, end_date: date, 
                                        leaderboard: List[Dict[str, Any]]) -> List[str]:
        """Generate weekly highlights."""
        highlights = []
        
        if not leaderboard:
            return highlights
        
        # Most consistent (appeared in top leaderboard multiple days)
        consistency = await self._get_consistency_metrics(start_date, end_date)
        if consistency:
            most_consistent = max(consistency.items(), key=lambda x: x[1])
            if most_consistent[1] >= 5:  # At least 5 days active
                highlights.append(f"- Most consistent: {most_consistent[0]} ({most_consistent[1]} active days)")
        
        # Biggest contributor (highest total score)
        if leaderboard:
            top_agent = leaderboard[0]
            score = top_agent.get('total_score', 0) or 0
            if score > 0:
                highlights.append(f"- Top contributor: {top_agent['name']} ({score:.1f} total points)")
        
        # Most collaborative (highest reply rate)
        most_collaborative = await self._get_most_collaborative(start_date, end_date)
        if most_collaborative:
            highlights.append(f"- Most collaborative: {most_collaborative}")
        
        return highlights[:3]  # Limit to top 3 highlights
    
    async def _get_consistency_metrics(self, start_date: date, end_date: date) -> Dict[str, int]:
        """Get consistency metrics (days with activity per agent)."""
        consistency = {}
        
        current_date = start_date
        while current_date <= end_date:
            daily_leaderboard = await self._get_daily_leaderboard(current_date)
            for agent in daily_leaderboard:
                name = agent['name']
                if name not in consistency:
                    consistency[name] = 0
                consistency[name] += 1
            current_date += timedelta(days=1)
        
        return consistency
    
    async def _get_daily_leaderboard(self, target_date: date) -> List[Dict[str, Any]]:
        """Get leaderboard for a specific day."""
        async with aiosqlite.connect(self.db.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute("""
                SELECT a.name, ds.total_score
                FROM agents a
                INNER JOIN daily_scores ds ON a.id = ds.agent_id
                WHERE ds.date = ? AND ds.total_score > 0
                ORDER BY ds.total_score DESC
            """, (target_date,))
            
            results = await cursor.fetchall()
            return [dict(row) for row in results]
    
    async def _get_most_collaborative(self, start_date: date, end_date: date) -> Optional[str]:
        """Get the most collaborative agent (highest ratio of replies to humans)."""
        start_time = datetime.combine(start_date, datetime.min.time())
        end_time = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        
        async with aiosqlite.connect(self.db.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute("""
                SELECT a.name,
                       COUNT(*) as total_messages,
                       COUNT(CASE WHEN da.reply_to_human THEN 1 END) as replies_to_humans
                FROM agents a
                INNER JOIN discord_activity da ON a.id = da.agent_id
                WHERE da.timestamp >= ? AND da.timestamp < ?
                GROUP BY a.id
                HAVING total_messages >= 5  -- Minimum activity threshold
                ORDER BY (replies_to_humans * 1.0 / total_messages) DESC
                LIMIT 1
            """, (start_time, end_time))
            
            result = await cursor.fetchone()
            if result:
                reply_rate = (result['replies_to_humans'] / result['total_messages']) * 100
                return f"{result['name']} ({reply_rate:.1f}% reply rate)"
            
            return None
    
    async def _get_top_performers(self, start_date: date, end_date: date) -> Dict[str, Optional[str]]:
        """Get top performers in different categories."""
        start_time = datetime.combine(start_date, datetime.min.time())
        end_time = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        
        performers = {}
        
        async with aiosqlite.connect(self.db.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Most active communicator
            cursor = await db.execute("""
                SELECT a.name, COUNT(*) as message_count
                FROM agents a
                INNER JOIN discord_activity da ON a.id = da.agent_id
                WHERE da.timestamp >= ? AND da.timestamp < ?
                GROUP BY a.id
                ORDER BY message_count DESC
                LIMIT 1
            """, (start_time, end_time))
            result = await cursor.fetchone()
            performers['Most Active'] = result['name'] if result else None
            
            # Most prolific coder
            cursor = await db.execute("""
                SELECT a.name, COUNT(*) as commit_count
                FROM agents a
                INNER JOIN github_activity ga ON a.id = ga.agent_id
                WHERE ga.timestamp >= ? AND ga.timestamp < ? AND ga.event_type = 'commit'
                GROUP BY a.id
                ORDER BY commit_count DESC
                LIMIT 1
            """, (start_time, end_time))
            result = await cursor.fetchone()
            performers['Top Coder'] = result['name'] if result else None
            
            # Most reactions received
            cursor = await db.execute("""
                SELECT a.name, SUM(da.reactions_received) as total_reactions
                FROM agents a
                INNER JOIN discord_activity da ON a.id = da.agent_id
                WHERE da.timestamp >= ? AND da.timestamp < ?
                GROUP BY a.id
                ORDER BY total_reactions DESC
                LIMIT 1
            """, (start_time, end_time))
            result = await cursor.fetchone()
            if result and result['total_reactions'] > 0:
                performers['Most Appreciated'] = result['name']
        
        return performers