"""Scoring engine for agent analytics."""
import math
from datetime import date, datetime, timedelta
from typing import Dict, List, Any, Set, Tuple, Optional
import aiosqlite
from .config import get_config
from .database import get_db


class ScoringEngine:
    """Quality-weighted scoring system for agent activities."""
    
    def __init__(self):
        self.config = get_config().scoring
    
    def score_discord_message(self, message_data: Dict[str, Any], 
                             unique_humans_today: Set[str]) -> Tuple[float, Dict[str, Any]]:
        """Score a Discord message with quality weighting."""
        score = 1.0  # Base message score
        metrics = {
            "base_message": 1.0,
            "code_bonus": 0.0,
            "length_bonus": 0.0,
            "reply_bonus": 0.0,
            "reaction_bonus": 0.0,
            "unique_human_bonus": 0.0
        }
        
        # Code block bonus
        if message_data.get('has_code', False):
            bonus = self.config.discord_code_block
            score += bonus
            metrics["code_bonus"] = bonus
        
        # Long message bonus (>200 chars with substance)
        if message_data.get('message_length', 0) > 200:
            bonus = self.config.discord_long_message
            score += bonus
            metrics["length_bonus"] = bonus
        
        # Human engagement bonus
        if message_data.get('reply_to_human', False):
            bonus = self.config.discord_reply_from_human
            score += bonus
            metrics["reply_bonus"] = bonus
        
        # Reaction bonus
        reactions = message_data.get('reactions_received', 0)
        if reactions > 0:
            bonus = reactions * self.config.discord_reaction
            score += bonus
            metrics["reaction_bonus"] = bonus
        
        # Note: unique humans bonus is calculated at daily level, not per message
        
        return score, metrics
    
    def score_github_event(self, event_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        """Score a GitHub event with quality weighting."""
        event_type = event_data.get('event_type', '')
        score = 0.0
        metrics = {"event_type": event_type}
        
        if event_type == 'commit':
            # Base commit score scaled by code changes
            additions = event_data.get('additions', 0)
            deletions = event_data.get('deletions', 0)
            changes = additions + deletions
            
            if changes > 0:
                # Scale by square root to prevent gaming with massive commits
                scale_factor = math.sqrt(changes)
                # Cap at maximum multiplier
                scale_factor = min(scale_factor, self.config.github_commit_max / self.config.github_commit_base)
                score = self.config.github_commit_base * scale_factor
            else:
                score = self.config.github_commit_base
            
            metrics.update({
                "base_score": self.config.github_commit_base,
                "scale_factor": scale_factor if changes > 0 else 1.0,
                "additions": additions,
                "deletions": deletions
            })
        
        elif event_type == 'pull_request':
            if event_data.get('was_merged', False):
                score = self.config.github_pr_merged
                metrics["status"] = "merged"
            else:
                score = self.config.github_pr_opened
                metrics["status"] = "opened"
        
        elif event_type == 'pull_request_review':
            score = self.config.github_pr_review
        
        elif event_type == 'issues':
            # Determine if opened or closed based on title/context
            title = event_data.get('title', '').lower()
            if 'closed' in title or event_data.get('was_merged', False):  # Reuse was_merged for closed status
                score = self.config.github_issue_closed
                metrics["status"] = "closed"
            else:
                score = self.config.github_issue_opened
                metrics["status"] = "opened"
        
        elif event_type == 'release':
            score = self.config.github_release
        
        metrics["score"] = score
        return score, metrics
    
    async def calculate_daily_scores(self, agent_id: int, target_date: date = None) -> Dict[str, Any]:
        """Calculate comprehensive daily scores for an agent."""
        if target_date is None:
            target_date = date.today()
        
        db = await get_db()
        
        # Get Discord activity for the day
        start_time = datetime.combine(target_date, datetime.min.time())
        end_time = start_time + timedelta(days=1)
        
        async with aiosqlite.connect(db.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            
            # Discord activities
            cursor = await conn.execute("""
                SELECT * FROM discord_activity
                WHERE agent_id = ? AND timestamp >= ? AND timestamp < ?
                ORDER BY timestamp
            """, (agent_id, start_time, end_time))
            discord_activities = [dict(row) for row in await cursor.fetchall()]
            
            # GitHub activities
            cursor = await conn.execute("""
                SELECT * FROM github_activity
                WHERE agent_id = ? AND timestamp >= ? AND timestamp < ?
                ORDER BY timestamp
            """, (agent_id, start_time, end_time))
            github_activities = [dict(row) for row in await cursor.fetchall()]
            
            # Get unique humans interacted with (for Discord)
            cursor = await conn.execute("""
                SELECT DISTINCT channel_id FROM discord_activity
                WHERE agent_id = ? AND timestamp >= ? AND timestamp < ?
                AND reply_to_human = TRUE
            """, (agent_id, start_time, end_time))
            unique_human_channels = {row[0] for row in await cursor.fetchall()}
        
        # Calculate Discord score
        discord_score = 0.0
        discord_metrics = {
            "messages": len(discord_activities),
            "messages_with_code": 0,
            "messages_with_reactions": 0,
            "total_reactions": 0,
            "unique_humans": len(unique_human_channels),
            "message_scores": []
        }
        
        for activity in discord_activities:
            msg_score, msg_metrics = self.score_discord_message(activity, unique_human_channels)
            discord_score += msg_score
            discord_metrics["message_scores"].append({
                "message_id": activity["message_id"],
                "score": msg_score,
                "metrics": msg_metrics
            })
            
            if activity.get('has_code'):
                discord_metrics["messages_with_code"] += 1
            
            reactions = activity.get('reactions_received', 0)
            if reactions > 0:
                discord_metrics["messages_with_reactions"] += 1
                discord_metrics["total_reactions"] += reactions
        
        # Add unique humans bonus to total Discord score
        if len(unique_human_channels) > 0:
            unique_bonus = len(unique_human_channels) * self.config.discord_unique_human
            discord_score += unique_bonus
            discord_metrics["unique_human_bonus"] = unique_bonus
        
        # Calculate GitHub score
        github_score = 0.0
        github_metrics = {
            "events": len(github_activities),
            "commits": 0,
            "prs_opened": 0,
            "prs_merged": 0,
            "issues_opened": 0,
            "issues_closed": 0,
            "releases": 0,
            "total_additions": 0,
            "total_deletions": 0,
            "event_scores": []
        }
        
        for activity in github_activities:
            event_score, event_metrics = self.score_github_event(activity)
            github_score += event_score
            github_metrics["event_scores"].append({
                "event_type": activity["event_type"],
                "repo": activity["repo"],
                "title": activity.get("title"),
                "score": event_score,
                "metrics": event_metrics
            })
            
            # Update counters
            event_type = activity.get('event_type', '')
            if event_type == 'commit':
                github_metrics["commits"] += 1
                github_metrics["total_additions"] += activity.get('additions', 0)
                github_metrics["total_deletions"] += activity.get('deletions', 0)
            elif event_type == 'pull_request':
                if activity.get('was_merged'):
                    github_metrics["prs_merged"] += 1
                else:
                    github_metrics["prs_opened"] += 1
            elif event_type == 'issues':
                if activity.get('was_merged'):  # Reused for closed status
                    github_metrics["issues_closed"] += 1
                else:
                    github_metrics["issues_opened"] += 1
            elif event_type == 'release':
                github_metrics["releases"] += 1
        
        # Calculate derived metrics
        merge_rate = 0.0
        if github_metrics["prs_opened"] + github_metrics["prs_merged"] > 0:
            merge_rate = github_metrics["prs_merged"] / (github_metrics["prs_opened"] + github_metrics["prs_merged"])
        
        total_score = discord_score + github_score
        
        return {
            "date": target_date.isoformat(),
            "discord_score": discord_score,
            "github_score": github_score,
            "total_score": total_score,
            "discord_metrics": discord_metrics,
            "github_metrics": github_metrics,
            "derived_metrics": {
                "merge_rate": merge_rate,
                "lines_changed": github_metrics["total_additions"] + github_metrics["total_deletions"],
                "avg_discord_score_per_message": discord_score / max(1, discord_metrics["messages"]),
                "avg_github_score_per_event": github_score / max(1, github_metrics["events"])
            }
        }
    
    async def update_all_daily_scores(self, target_date: date = None) -> List[Dict[str, Any]]:
        """Update daily scores for all agents."""
        if target_date is None:
            target_date = date.today()
        
        db = await get_db()
        agents = await db.get_agents()
        
        results = []
        for agent in agents:
            scores = await self.calculate_daily_scores(agent['id'], target_date)
            
            # Store in database
            await db.update_daily_scores(
                agent_id=agent['id'],
                date=target_date,
                discord_score=scores['discord_score'],
                github_score=scores['github_score'],
                metrics={
                    "discord_metrics": scores['discord_metrics'],
                    "github_metrics": scores['github_metrics'],
                    "derived_metrics": scores['derived_metrics']
                }
            )
            
            results.append({
                "agent": agent,
                "scores": scores
            })
        
        return results


# Global scoring engine instance
_scoring_engine: Optional[ScoringEngine] = None


def get_scoring_engine() -> ScoringEngine:
    """Get the global scoring engine instance."""
    global _scoring_engine
    if _scoring_engine is None:
        _scoring_engine = ScoringEngine()
    return _scoring_engine