"""Tests for the scoring engine."""
import unittest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, date
import sys
from pathlib import Path

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.scoring import ScoringEngine
from src.config import ScoringConfig


class TestScoringEngine(unittest.TestCase):
    """Test cases for the scoring engine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.scoring_engine = ScoringEngine()
        # Mock the config
        self.scoring_engine.config = ScoringConfig()
    
    def test_discord_message_base_score(self):
        """Test basic Discord message scoring."""
        message_data = {
            'message_length': 50,
            'has_code': False,
            'has_media': False,
            'reply_to_human': False,
            'reactions_received': 0
        }
        
        score, metrics = self.scoring_engine.score_discord_message(message_data, set())
        
        self.assertEqual(score, 1.0)  # Base score
        self.assertEqual(metrics['base_message'], 1.0)
        self.assertEqual(metrics['code_bonus'], 0.0)
    
    def test_discord_message_with_code(self):
        """Test Discord message with code bonus."""
        message_data = {
            'message_length': 50,
            'has_code': True,
            'has_media': False,
            'reply_to_human': False,
            'reactions_received': 0
        }
        
        score, metrics = self.scoring_engine.score_discord_message(message_data, set())
        
        self.assertEqual(score, 1.5)  # Base + code bonus
        self.assertEqual(metrics['code_bonus'], 0.5)
    
    def test_discord_message_long_with_substance(self):
        """Test Discord long message bonus."""
        message_data = {
            'message_length': 250,
            'has_code': False,
            'has_media': False,
            'reply_to_human': False,
            'reactions_received': 0
        }
        
        score, metrics = self.scoring_engine.score_discord_message(message_data, set())
        
        self.assertEqual(score, 1.3)  # Base + length bonus
        self.assertEqual(metrics['length_bonus'], 0.3)
    
    def test_discord_message_with_human_reply(self):
        """Test Discord message with human reply bonus."""
        message_data = {
            'message_length': 50,
            'has_code': False,
            'has_media': False,
            'reply_to_human': True,
            'reactions_received': 0
        }
        
        score, metrics = self.scoring_engine.score_discord_message(message_data, set())
        
        self.assertEqual(score, 2.0)  # Base + reply bonus
        self.assertEqual(metrics['reply_bonus'], 1.0)
    
    def test_discord_message_with_reactions(self):
        """Test Discord message with reactions."""
        message_data = {
            'message_length': 50,
            'has_code': False,
            'has_media': False,
            'reply_to_human': False,
            'reactions_received': 3
        }
        
        score, metrics = self.scoring_engine.score_discord_message(message_data, set())
        
        self.assertEqual(score, 1.9)  # Base + 3 * 0.3 reaction bonus
        self.assertEqual(metrics['reaction_bonus'], 0.9)
    
    def test_github_commit_scoring(self):
        """Test GitHub commit scoring."""
        event_data = {
            'event_type': 'commit',
            'additions': 100,
            'deletions': 50,
        }
        
        score, metrics = self.scoring_engine.score_github_event(event_data)
        
        # Should be base * sqrt(150) capped at max
        import math
        expected_scale = math.sqrt(150)
        expected_score = min(1.0 * expected_scale, 5.0)
        
        self.assertAlmostEqual(score, expected_score, places=2)
        self.assertEqual(metrics['event_type'], 'commit')
        self.assertEqual(metrics['additions'], 100)
        self.assertEqual(metrics['deletions'], 50)
    
    def test_github_pr_opened_scoring(self):
        """Test GitHub PR opened scoring."""
        event_data = {
            'event_type': 'pull_request',
            'was_merged': False
        }
        
        score, metrics = self.scoring_engine.score_github_event(event_data)
        
        self.assertEqual(score, 2.0)
        self.assertEqual(metrics['status'], 'opened')
    
    def test_github_pr_merged_scoring(self):
        """Test GitHub PR merged scoring."""
        event_data = {
            'event_type': 'pull_request',
            'was_merged': True
        }
        
        score, metrics = self.scoring_engine.score_github_event(event_data)
        
        self.assertEqual(score, 5.0)
        self.assertEqual(metrics['status'], 'merged')
    
    def test_github_pr_review_scoring(self):
        """Test GitHub PR review scoring."""
        event_data = {
            'event_type': 'pull_request_review'
        }
        
        score, metrics = self.scoring_engine.score_github_event(event_data)
        
        self.assertEqual(score, 1.5)
        self.assertEqual(metrics['event_type'], 'pull_request_review')
    
    def test_github_issue_opened_scoring(self):
        """Test GitHub issue opened scoring."""
        event_data = {
            'event_type': 'issues',
            'was_merged': False,  # Used for closed status
            'title': 'New issue'
        }
        
        score, metrics = self.scoring_engine.score_github_event(event_data)
        
        self.assertEqual(score, 1.0)
        self.assertEqual(metrics['status'], 'opened')
    
    def test_github_issue_closed_scoring(self):
        """Test GitHub issue closed scoring."""
        event_data = {
            'event_type': 'issues',
            'was_merged': True,  # Used for closed status
            'title': 'Closed issue'
        }
        
        score, metrics = self.scoring_engine.score_github_event(event_data)
        
        self.assertEqual(score, 2.0)
        self.assertEqual(metrics['status'], 'closed')
    
    def test_github_release_scoring(self):
        """Test GitHub release scoring."""
        event_data = {
            'event_type': 'release'
        }
        
        score, metrics = self.scoring_engine.score_github_event(event_data)
        
        self.assertEqual(score, 3.0)
        self.assertEqual(metrics['event_type'], 'release')
    
    def test_unknown_github_event(self):
        """Test unknown GitHub event type."""
        event_data = {
            'event_type': 'unknown_event'
        }
        
        score, metrics = self.scoring_engine.score_github_event(event_data)
        
        self.assertEqual(score, 0.0)
        self.assertEqual(metrics['event_type'], 'unknown_event')


if __name__ == '__main__':
    unittest.main()