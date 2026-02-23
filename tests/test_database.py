"""Tests for the database module."""
import unittest
import asyncio
import tempfile
import os
from datetime import datetime, date
import sys
from pathlib import Path

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.database import Database


class TestDatabase(unittest.IsolatedAsyncioTestCase):
    """Test cases for the database operations."""
    
    async def asyncSetUp(self):
        """Set up test database."""
        # Create temporary database file
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        
        self.db = Database(self.temp_db.name)
        await self.db.init_db()
    
    async def asyncTearDown(self):
        """Clean up test database."""
        os.unlink(self.temp_db.name)
    
    async def test_init_db(self):
        """Test database initialization."""
        # Database should be initialized without errors
        # Check if tables exist by trying to query them
        import aiosqlite
        async with aiosqlite.connect(self.db.db_path) as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] async for row in cursor}
            
            expected_tables = {
                'agents', 
                'discord_activity', 
                'github_activity', 
                'daily_scores'
            }
            
            self.assertTrue(expected_tables.issubset(tables))
    
    async def test_upsert_agent(self):
        """Test agent upsert operations."""
        # Insert new agent
        agent_id = await self.db.upsert_agent(
            name="Test Agent",
            discord_id="123456789",
            github_username="testagent"
        )
        
        self.assertIsNotNone(agent_id)
        self.assertIsInstance(agent_id, int)
        
        # Update existing agent
        agent_id2 = await self.db.upsert_agent(
            name="Test Agent",
            discord_id="123456789",
            github_username="updated_username"
        )
        
        self.assertEqual(agent_id, agent_id2)
        
        # Verify update
        agent = await self.db.get_agent_by_discord_id("123456789")
        self.assertEqual(agent['github_username'], "updated_username")
    
    async def test_get_agent_by_discord_id(self):
        """Test retrieving agent by Discord ID."""
        # Insert agent
        await self.db.upsert_agent(
            name="Discord Agent",
            discord_id="987654321",
            github_username="discordagent"
        )
        
        # Retrieve agent
        agent = await self.db.get_agent_by_discord_id("987654321")
        
        self.assertIsNotNone(agent)
        self.assertEqual(agent['name'], "Discord Agent")
        self.assertEqual(agent['discord_id'], "987654321")
        self.assertEqual(agent['github_username'], "discordagent")
        
        # Test non-existent agent
        agent = await self.db.get_agent_by_discord_id("000000000")
        self.assertIsNone(agent)
    
    async def test_get_agent_by_github_username(self):
        """Test retrieving agent by GitHub username."""
        # Insert agent
        await self.db.upsert_agent(
            name="GitHub Agent",
            discord_id="111111111",
            github_username="githubagent"
        )
        
        # Retrieve agent
        agent = await self.db.get_agent_by_github_username("githubagent")
        
        self.assertIsNotNone(agent)
        self.assertEqual(agent['name'], "GitHub Agent")
        self.assertEqual(agent['github_username'], "githubagent")
        
        # Test non-existent agent
        agent = await self.db.get_agent_by_github_username("nonexistent")
        self.assertIsNone(agent)
    
    async def test_add_discord_activity(self):
        """Test adding Discord activity."""
        # Create agent first
        agent_id = await self.db.upsert_agent(
            name="Activity Agent",
            discord_id="222222222"
        )
        
        # Add Discord activity
        await self.db.add_discord_activity(
            agent_id=agent_id,
            channel_id="333333333",
            channel_name="general",
            guild_id="444444444",
            message_id="555555555",
            message_length=100,
            has_code=True,
            has_media=False,
            reply_to_human=True,
            reactions_received=3
        )
        
        # Verify activity was added
        activity = await self.db.get_agent_activity(agent_id, days=1)
        discord_activities = activity['discord_activity']
        
        self.assertEqual(len(discord_activities), 1)
        
        activity_record = discord_activities[0]
        self.assertEqual(activity_record['channel_id'], "333333333")
        self.assertEqual(activity_record['message_length'], 100)
        self.assertTrue(activity_record['has_code'])
        self.assertFalse(activity_record['has_media'])
        self.assertTrue(activity_record['reply_to_human'])
        self.assertEqual(activity_record['reactions_received'], 3)
    
    async def test_add_github_activity(self):
        """Test adding GitHub activity."""
        # Create agent first
        agent_id = await self.db.upsert_agent(
            name="GitHub Activity Agent",
            github_username="githubactivity"
        )
        
        # Add GitHub activity
        await self.db.add_github_activity(
            agent_id=agent_id,
            repo="test/repo",
            event_type="commit",
            title="Test commit",
            additions=50,
            deletions=10,
            files_changed=3
        )
        
        # Verify activity was added
        activity = await self.db.get_agent_activity(agent_id, days=1)
        github_activities = activity['github_activity']
        
        self.assertEqual(len(github_activities), 1)
        
        activity_record = github_activities[0]
        self.assertEqual(activity_record['repo'], "test/repo")
        self.assertEqual(activity_record['event_type'], "commit")
        self.assertEqual(activity_record['title'], "Test commit")
        self.assertEqual(activity_record['additions'], 50)
        self.assertEqual(activity_record['deletions'], 10)
        self.assertEqual(activity_record['files_changed'], 3)
    
    async def test_update_daily_scores(self):
        """Test updating daily scores."""
        # Create agent first
        agent_id = await self.db.upsert_agent(name="Score Agent")
        
        # Update daily scores
        test_date = date.today()
        discord_score = 15.5
        github_score = 8.3
        metrics = {
            "messages": 10,
            "commits": 3,
            "total_reactions": 5
        }
        
        await self.db.update_daily_scores(
            agent_id=agent_id,
            date=test_date,
            discord_score=discord_score,
            github_score=github_score,
            metrics=metrics
        )
        
        # Verify scores were updated
        activity = await self.db.get_agent_activity(agent_id, days=1)
        daily_scores = activity['daily_scores']
        
        self.assertEqual(len(daily_scores), 1)
        
        score_record = daily_scores[0]
        self.assertEqual(score_record['discord_score'], discord_score)
        self.assertEqual(score_record['github_score'], github_score)
        self.assertEqual(score_record['total_score'], discord_score + github_score)
        
        # Test upsert (update existing record)
        new_discord_score = 20.0
        await self.db.update_daily_scores(
            agent_id=agent_id,
            date=test_date,
            discord_score=new_discord_score,
            github_score=github_score,
            metrics=metrics
        )
        
        # Should still have only one record with updated score
        activity = await self.db.get_agent_activity(agent_id, days=1)
        daily_scores = activity['daily_scores']
        
        self.assertEqual(len(daily_scores), 1)
        self.assertEqual(daily_scores[0]['discord_score'], new_discord_score)
    
    async def test_get_agents(self):
        """Test retrieving all agents."""
        # Add multiple agents
        await self.db.upsert_agent(name="Agent 1", discord_id="111")
        await self.db.upsert_agent(name="Agent 2", github_username="agent2")
        await self.db.upsert_agent(name="Agent 3", discord_id="333", github_username="agent3")
        
        agents = await self.db.get_agents()
        
        self.assertEqual(len(agents), 3)
        
        agent_names = {agent['name'] for agent in agents}
        expected_names = {"Agent 1", "Agent 2", "Agent 3"}
        self.assertEqual(agent_names, expected_names)
    
    async def test_get_activity_stats(self):
        """Test getting activity statistics."""
        # Create agent and add activities
        agent_id = await self.db.upsert_agent(name="Stats Agent")
        
        # Add Discord activities
        await self.db.add_discord_activity(
            agent_id=agent_id,
            channel_id="111",
            channel_name="general",
            guild_id="222",
            message_id="333",
            message_length=50,
            has_code=True,
            reactions_received=2
        )
        
        await self.db.add_discord_activity(
            agent_id=agent_id,
            channel_id="111",
            channel_name="general",
            guild_id="222",
            message_id="444",
            message_length=30,
            has_code=False,
            reactions_received=1
        )
        
        # Add GitHub activities
        await self.db.add_github_activity(
            agent_id=agent_id,
            repo="test/repo",
            event_type="commit",
            title="Commit 1"
        )
        
        await self.db.add_github_activity(
            agent_id=agent_id,
            repo="test/repo",
            event_type="pull_request",
            title="PR 1",
            was_merged=True
        )
        
        # Get stats
        stats = await self.db.get_activity_stats(days=1)
        
        discord_stats = stats['discord']
        github_stats = stats['github']
        
        self.assertEqual(discord_stats['total_messages'], 2)
        self.assertEqual(discord_stats['messages_with_code'], 1)
        self.assertEqual(discord_stats['total_reactions'], 3)
        
        self.assertEqual(github_stats['total_events'], 2)
        self.assertEqual(github_stats['commits'], 1)
        self.assertEqual(github_stats['prs'], 1)
        self.assertEqual(github_stats['merged_prs'], 1)


if __name__ == '__main__':
    unittest.main()