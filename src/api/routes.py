"""FastAPI routes for the agent analytics dashboard."""
import hashlib
import hmac
import os
import secrets
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, Depends, Response, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import json

from ..config import get_config
from ..database import get_db
from ..collectors.github import get_github_collector
from ..scoring import get_scoring_engine


# Initialize FastAPI app
app = FastAPI(
    title="Agent Analytics Dashboard",
    description="Analytics dashboard for AI agent activity tracking",
    version="1.0.0"
)

# --- Authentication ---
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))
COOKIE_NAME = "aa_session"


def _make_session_token(password: str) -> str:
    """Create a session token from the password."""
    return hmac.new(SESSION_SECRET.encode(), password.encode(), hashlib.sha256).hexdigest()


def _auth_required(request: Request) -> bool:
    """Check if password protection is enabled and request is authenticated."""
    if not DASHBOARD_PASSWORD:
        return True  # No password set, allow all
    token = request.cookies.get(COOKIE_NAME, "")
    expected = _make_session_token(DASHBOARD_PASSWORD)
    return hmac.compare_digest(token, expected)


async def require_auth(request: Request):
    """Dependency that enforces authentication on protected routes."""
    if not _auth_required(request):
        # For API routes, return 401
        if request.url.path.startswith("/api/") or request.url.path.startswith("/webhooks/"):
            raise HTTPException(status_code=401, detail="Unauthorized")
        # For page routes, redirect to login
        raise HTTPException(status_code=303, headers={"Location": "/login"})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    """Serve login page."""
    if not DASHBOARD_PASSWORD:
        return RedirectResponse("/")
    if _auth_required(request):
        return RedirectResponse("/")
    error_html = f'<p style="color:#e74c3c;margin-bottom:16px">{error}</p>' if error else ""
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html><head>
        <title>Agent Analytics - Login</title>
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📊</text></svg>">
        <style>
            body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
                   background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
                   min-height:100vh;display:flex;align-items:center;justify-content:center; }}
            .card {{ background:#fff;padding:40px;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,.15);
                    width:340px;text-align:center; }}
            h2 {{ color:#333;margin-bottom:24px; }}
            input {{ width:100%;padding:12px;border:1px solid #ddd;border-radius:8px;font-size:1rem;
                    margin-bottom:16px;box-sizing:border-box; }}
            button {{ width:100%;padding:12px;background:#667eea;color:#fff;border:none;border-radius:8px;
                     font-size:1rem;cursor:pointer;font-weight:600; }}
            button:hover {{ background:#5a6fd6; }}
        </style>
    </head><body>
        <div class="card">
            <h2>📊 Agent Analytics</h2>
            {error_html}
            <form method="POST" action="/login">
                <input type="password" name="password" placeholder="Password" autofocus required>
                <button type="submit">Sign In</button>
            </form>
        </div>
    </body></html>
    """)


@app.post("/login")
async def login_submit(request: Request):
    """Handle login form submission."""
    form = await request.form()
    password = form.get("password", "")
    if not DASHBOARD_PASSWORD or password != DASHBOARD_PASSWORD:
        return RedirectResponse("/login?error=Invalid+password", status_code=303)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE_NAME, _make_session_token(DASHBOARD_PASSWORD),
                        httponly=True, samesite="lax", max_age=86400 * 30)
    return response


@app.get("/logout")
async def logout():
    """Clear session."""
    response = RedirectResponse("/login")
    response.delete_cookie(COOKIE_NAME)
    return response

# Templates
templates = Jinja2Templates(directory="src/templates")

# Global dependencies
async def get_database():
    return await get_db()

async def get_github_collector_dep():
    return await get_github_collector()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db=Depends(get_database), _=Depends(require_auth)):
    """Serve the main dashboard page."""
    # Get basic stats for the dashboard
    agents = await db.get_agents()
    leaderboard = await db.get_leaderboard(period="day", limit=10)
    activity_stats = await db.get_activity_stats(days=7)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "agents_count": len(agents),
        "total_discord_messages": activity_stats.get('discord', {}).get('total_messages', 0),
        "total_github_commits": activity_stats.get('github', {}).get('commits', 0),
        "top_agent": leaderboard[0]['name'] if leaderboard else "No activity"
    })


@app.get("/api/agents")
async def get_agents(db=Depends(get_database), _=Depends(require_auth)) -> List[Dict[str, Any]]:
    """Get all tracked agents."""
    agents = await db.get_agents()
    return agents


@app.get("/api/leaderboard")
async def get_leaderboard(
    period: str = "day",
    limit: int = 10,
    db=Depends(get_database),
    _=Depends(require_auth)
) -> List[Dict[str, Any]]:
    """Get leaderboard for specified period."""
    if period not in ["day", "week", "month"]:
        raise HTTPException(status_code=400, detail="Period must be 'day', 'week', or 'month'")
    
    if limit > 50:
        raise HTTPException(status_code=400, detail="Limit cannot exceed 50")
    
    leaderboard = await db.get_leaderboard(period=period, limit=limit)
    return leaderboard


@app.get("/api/agent/{agent_id}/activity")
async def get_agent_activity(
    agent_id: int,
    days: int = 7,
    db=Depends(get_database),
    _=Depends(require_auth)
) -> Dict[str, Any]:
    """Get detailed activity for a specific agent."""
    if days > 90:
        raise HTTPException(status_code=400, detail="Days cannot exceed 90")
    
    # Check if agent exists
    agents = await db.get_agents()
    agent = next((a for a in agents if a['id'] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    activity = await db.get_agent_activity(agent_id, days=days)
    
    # Add agent info to response
    activity['agent'] = agent
    
    return activity


@app.get("/api/stats")
async def get_stats(days: int = 7, db=Depends(get_database), _=Depends(require_auth)) -> Dict[str, Any]:
    """Get aggregate statistics."""
    if days > 365:
        raise HTTPException(status_code=400, detail="Days cannot exceed 365")
    
    activity_stats = await db.get_activity_stats(days=days)
    agents = await db.get_agents()
    
    return {
        "period_days": days,
        "total_agents": len(agents),
        "activity_stats": activity_stats,
        "generated_at": date.today().isoformat()
    }


@app.get("/api/charts/leaderboard")
async def get_leaderboard_chart_data(
    period: str = "day",
    limit: int = 10,
    db=Depends(get_database),
    _=Depends(require_auth)
) -> Dict[str, Any]:
    """Get leaderboard data formatted for Chart.js."""
    leaderboard = await db.get_leaderboard(period=period, limit=limit)
    
    labels = [agent['name'] for agent in leaderboard]
    discord_scores = [agent.get('discord_score', 0) or 0 for agent in leaderboard]
    github_scores = [agent.get('github_score', 0) or 0 for agent in leaderboard]
    total_scores = [agent.get('total_score', 0) or 0 for agent in leaderboard]
    
    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Discord Score",
                "data": discord_scores,
                "backgroundColor": "rgba(114, 137, 218, 0.8)",
                "borderColor": "rgba(114, 137, 218, 1)",
                "borderWidth": 1
            },
            {
                "label": "GitHub Score", 
                "data": github_scores,
                "backgroundColor": "rgba(36, 41, 46, 0.8)",
                "borderColor": "rgba(36, 41, 46, 1)",
                "borderWidth": 1
            }
        ]
    }


@app.get("/api/charts/activity-timeline")
async def get_activity_timeline(
    days: int = 30,
    db=Depends(get_database),
    _=Depends(require_auth)
) -> Dict[str, Any]:
    """Get activity timeline data for Chart.js."""
    if days > 90:
        raise HTTPException(status_code=400, detail="Days cannot exceed 90")
    
    # Get daily activity for the past N days
    end_date = date.today()
    start_date = end_date - timedelta(days=days-1)
    
    labels = []
    discord_data = []
    github_data = []
    
    current_date = start_date
    while current_date <= end_date:
        labels.append(current_date.strftime("%m/%d"))
        
        # Get activity stats for this day
        activity_stats = await db.get_activity_stats(days=1)  # This gets yesterday, need to fix this
        
        # For now, use placeholder data - in production you'd query by specific date
        discord_data.append(activity_stats.get('discord', {}).get('total_messages', 0))
        github_data.append(activity_stats.get('github', {}).get('total_events', 0))
        
        current_date += timedelta(days=1)
    
    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Discord Messages",
                "data": discord_data,
                "borderColor": "rgba(114, 137, 218, 1)",
                "backgroundColor": "rgba(114, 137, 218, 0.1)",
                "tension": 0.4
            },
            {
                "label": "GitHub Events",
                "data": github_data,
                "borderColor": "rgba(36, 41, 46, 1)",
                "backgroundColor": "rgba(36, 41, 46, 0.1)",
                "tension": 0.4
            }
        ]
    }


@app.get("/api/charts/agent/{agent_id}/scores")
async def get_agent_scores_chart(
    agent_id: int,
    days: int = 30,
    db=Depends(get_database),
    _=Depends(require_auth)
) -> Dict[str, Any]:
    """Get agent score timeline for Chart.js."""
    # Check if agent exists
    agents = await db.get_agents()
    agent = next((a for a in agents if a['id'] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Get daily scores for the agent
    activity = await db.get_agent_activity(agent_id, days=days)
    daily_scores = activity.get('daily_scores', [])
    
    # Sort by date
    daily_scores.sort(key=lambda x: x['date'])
    
    labels = [score['date'] for score in daily_scores]
    discord_scores = [score['discord_score'] for score in daily_scores]
    github_scores = [score['github_score'] for score in daily_scores]
    total_scores = [score['total_score'] for score in daily_scores]
    
    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Discord Score",
                "data": discord_scores,
                "borderColor": "rgba(114, 137, 218, 1)",
                "backgroundColor": "rgba(114, 137, 218, 0.1)",
                "tension": 0.4
            },
            {
                "label": "GitHub Score",
                "data": github_scores,
                "borderColor": "rgba(36, 41, 46, 1)",
                "backgroundColor": "rgba(36, 41, 46, 0.1)",
                "tension": 0.4
            },
            {
                "label": "Total Score",
                "data": total_scores,
                "borderColor": "rgba(46, 204, 113, 1)",
                "backgroundColor": "rgba(46, 204, 113, 0.1)",
                "tension": 0.4
            }
        ]
    }


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    github_collector=Depends(get_github_collector_dep)
) -> JSONResponse:
    """Handle GitHub webhook events."""
    try:
        result = await github_collector.handle_webhook(request)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/calculate-scores")
async def calculate_scores(
    target_date: Optional[str] = None,
    db=Depends(get_database),
    _=Depends(require_auth)
) -> Dict[str, Any]:
    """Manually trigger score calculation for a specific date."""
    scoring_engine = get_scoring_engine()
    
    if target_date:
        try:
            target = date.fromisoformat(target_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        target = date.today()
    
    results = await scoring_engine.update_all_daily_scores(target)
    
    return {
        "date": target.isoformat(),
        "agents_processed": len(results),
        "results": [
            {
                "agent_name": result["agent"]["name"],
                "discord_score": result["scores"]["discord_score"],
                "github_score": result["scores"]["github_score"],
                "total_score": result["scores"]["total_score"]
            }
            for result in results
        ]
    }


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=404,
        content={"error": "Not found", "detail": "The requested resource was not found"}
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": "An unexpected error occurred"}
    )