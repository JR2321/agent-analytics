"""GitHub webhook handler and activity collector."""
import hashlib
import hmac
import json
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import Request, HTTPException

from ..config import get_config
from ..database import get_db


class GitHubCollector:
    """Handles GitHub webhook events and activity collection."""
    
    def __init__(self):
        self.config = get_config()
        self.db = None
        
        # Cache for GitHub username to agent ID mapping
        self._username_cache: Dict[str, int] = {}
    
    async def init(self):
        """Initialize the collector."""
        self.db = await get_db()
        await self._build_username_cache()
    
    async def _build_username_cache(self):
        """Build cache of GitHub username to agent ID mapping."""
        agents = await self.db.get_agents()
        for agent in agents:
            if agent.get('github_username'):
                self._username_cache[agent['github_username']] = agent['id']
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify GitHub webhook signature."""
        if not self.config.github.webhook_secret:
            return True  # Skip verification if no secret configured
        
        expected_signature = hmac.new(
            self.config.github.webhook_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(f"sha256={expected_signature}", signature)
    
    async def handle_webhook(self, request: Request) -> Dict[str, Any]:
        """Handle incoming GitHub webhook."""
        # Verify signature
        signature = request.headers.get('X-Hub-Signature-256', '')
        payload = await request.body()
        
        if not self.verify_webhook_signature(payload, signature):
            raise HTTPException(status_code=403, detail="Invalid signature")
        
        # Parse payload
        try:
            data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
        event_type = request.headers.get('X-GitHub-Event', '')
        
        # Process different event types
        result = {"processed": False, "events": []}
        
        if event_type == "push":
            events = await self._handle_push_event(data)
            result["events"].extend(events)
        elif event_type == "pull_request":
            events = await self._handle_pull_request_event(data)
            result["events"].extend(events)
        elif event_type == "issues":
            events = await self._handle_issues_event(data)
            result["events"].extend(events)
        elif event_type == "pull_request_review":
            events = await self._handle_pull_request_review_event(data)
            result["events"].extend(events)
        elif event_type == "release":
            events = await self._handle_release_event(data)
            result["events"].extend(events)
        else:
            print(f"Unhandled GitHub event type: {event_type}")
        
        result["processed"] = len(result["events"]) > 0
        return result
    
    async def _handle_push_event(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle push events (commits)."""
        events = []
        commits = data.get('commits', [])
        repo_name = data.get('repository', {}).get('full_name', '')
        
        # Filter tracked repos if configured
        if (self.config.github.tracked_repos and 
            repo_name not in self.config.github.tracked_repos):
            return events
        
        for commit in commits:
            author = commit.get('author', {})
            username = author.get('username')
            
            if not username or username not in self._username_cache:
                continue
            
            agent_id = self._username_cache[username]
            
            # Parse commit stats (GitHub doesn't provide this in push webhooks)
            # We'll estimate or fetch separately if needed
            additions = 0
            deletions = 0
            files_changed = len(commit.get('modified', []) + commit.get('added', []) + commit.get('removed', []))
            
            timestamp = datetime.fromisoformat(commit.get('timestamp', '').replace('Z', '+00:00'))
            
            await self.db.add_github_activity(
                agent_id=agent_id,
                repo=repo_name,
                event_type="commit",
                title=commit.get('message', '')[:200],  # Truncate long commit messages
                additions=additions,
                deletions=deletions,
                files_changed=files_changed,
                timestamp=timestamp
            )
            
            events.append({
                "type": "commit",
                "agent_id": agent_id,
                "repo": repo_name,
                "commit_sha": commit.get('id', ''),
                "message": commit.get('message', ''),
                "files_changed": files_changed
            })
        
        return events
    
    async def _handle_pull_request_event(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle pull request events."""
        events = []
        action = data.get('action', '')
        
        if action not in ['opened', 'closed']:
            return events
        
        pull_request = data.get('pull_request', {})
        user = pull_request.get('user', {})
        username = user.get('login')
        repo_name = data.get('repository', {}).get('full_name', '')
        
        # Filter tracked repos if configured
        if (self.config.github.tracked_repos and 
            repo_name not in self.config.github.tracked_repos):
            return events
        
        if not username or username not in self._username_cache:
            return events
        
        agent_id = self._username_cache[username]
        was_merged = action == 'closed' and pull_request.get('merged', False)
        
        # Get PR stats
        additions = pull_request.get('additions', 0)
        deletions = pull_request.get('deletions', 0)
        files_changed = pull_request.get('changed_files', 0)
        
        timestamp = datetime.fromisoformat(
            pull_request.get('created_at' if action == 'opened' else 'closed_at', '')
            .replace('Z', '+00:00')
        )
        
        await self.db.add_github_activity(
            agent_id=agent_id,
            repo=repo_name,
            event_type="pull_request",
            title=pull_request.get('title', ''),
            additions=additions,
            deletions=deletions,
            files_changed=files_changed,
            was_merged=was_merged,
            timestamp=timestamp
        )
        
        events.append({
            "type": "pull_request",
            "action": action,
            "agent_id": agent_id,
            "repo": repo_name,
            "pr_number": pull_request.get('number', 0),
            "title": pull_request.get('title', ''),
            "was_merged": was_merged,
            "additions": additions,
            "deletions": deletions,
            "files_changed": files_changed
        })
        
        return events
    
    async def _handle_issues_event(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle issues events."""
        events = []
        action = data.get('action', '')
        
        if action not in ['opened', 'closed']:
            return events
        
        issue = data.get('issue', {})
        user = issue.get('user', {})
        username = user.get('login')
        repo_name = data.get('repository', {}).get('full_name', '')
        
        # Filter tracked repos if configured
        if (self.config.github.tracked_repos and 
            repo_name not in self.config.github.tracked_repos):
            return events
        
        if not username or username not in self._username_cache:
            return events
        
        agent_id = self._username_cache[username]
        was_merged = action == 'closed'  # Reuse field for closed status
        
        timestamp = datetime.fromisoformat(
            issue.get('created_at' if action == 'opened' else 'closed_at', '')
            .replace('Z', '+00:00')
        )
        
        await self.db.add_github_activity(
            agent_id=agent_id,
            repo=repo_name,
            event_type="issues",
            title=issue.get('title', ''),
            was_merged=was_merged,
            timestamp=timestamp
        )
        
        events.append({
            "type": "issues",
            "action": action,
            "agent_id": agent_id,
            "repo": repo_name,
            "issue_number": issue.get('number', 0),
            "title": issue.get('title', ''),
            "was_closed": was_merged
        })
        
        return events
    
    async def _handle_pull_request_review_event(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle pull request review events."""
        events = []
        action = data.get('action', '')
        
        if action != 'submitted':
            return events
        
        review = data.get('review', {})
        user = review.get('user', {})
        username = user.get('login')
        repo_name = data.get('repository', {}).get('full_name', '')
        
        # Filter tracked repos if configured
        if (self.config.github.tracked_repos and 
            repo_name not in self.config.github.tracked_repos):
            return events
        
        if not username or username not in self._username_cache:
            return events
        
        agent_id = self._username_cache[username]
        pull_request = data.get('pull_request', {})
        
        timestamp = datetime.fromisoformat(
            review.get('submitted_at', '').replace('Z', '+00:00')
        )
        
        await self.db.add_github_activity(
            agent_id=agent_id,
            repo=repo_name,
            event_type="pull_request_review",
            title=f"Review on PR #{pull_request.get('number', 0)}",
            timestamp=timestamp
        )
        
        events.append({
            "type": "pull_request_review",
            "agent_id": agent_id,
            "repo": repo_name,
            "pr_number": pull_request.get('number', 0),
            "review_state": review.get('state', '')
        })
        
        return events
    
    async def _handle_release_event(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle release events."""
        events = []
        action = data.get('action', '')
        
        if action != 'published':
            return events
        
        release = data.get('release', {})
        author = release.get('author', {})
        username = author.get('login')
        repo_name = data.get('repository', {}).get('full_name', '')
        
        # Filter tracked repos if configured
        if (self.config.github.tracked_repos and 
            repo_name not in self.config.github.tracked_repos):
            return events
        
        if not username or username not in self._username_cache:
            return events
        
        agent_id = self._username_cache[username]
        
        timestamp = datetime.fromisoformat(
            release.get('published_at', '').replace('Z', '+00:00')
        )
        
        await self.db.add_github_activity(
            agent_id=agent_id,
            repo=repo_name,
            event_type="release",
            title=release.get('name', '') or release.get('tag_name', ''),
            timestamp=timestamp
        )
        
        events.append({
            "type": "release",
            "agent_id": agent_id,
            "repo": repo_name,
            "tag_name": release.get('tag_name', ''),
            "name": release.get('name', '')
        })
        
        return events
    
    async def refresh_agent_cache(self):
        """Refresh the username to agent ID cache."""
        await self._build_username_cache()


# Global GitHub collector instance
_github_collector: Optional[GitHubCollector] = None


async def get_github_collector() -> GitHubCollector:
    """Get the global GitHub collector instance."""
    global _github_collector
    if _github_collector is None:
        _github_collector = GitHubCollector()
        await _github_collector.init()
    return _github_collector