#!/usr/bin/env python3
"""Main entry point for the Agent Analytics Dashboard."""

import asyncio
import argparse
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.config import load_config, set_config
from src.database import get_db
from src.collectors.discord_bot import run_discord_bot
from src.collectors.github import get_github_collector
from src.scoring import get_scoring_engine
from src.api.routes import app


async def init_database():
    """Initialize the database with required tables."""
    print("🗄️  Initializing database...")
    db = await get_db()
    print("✅ Database initialized successfully")


async def run_discord():
    """Run the Discord bot."""
    print("🤖 Starting Discord bot...")
    await run_discord_bot()


async def run_web():
    """Run the web dashboard."""
    import uvicorn
    from src.config import get_config
    
    print("🌐 Starting web dashboard...")
    
    # Initialize dependencies
    await init_database()
    github_collector = await get_github_collector()
    
    config = get_config()
    
    # Run the web server
    uvicorn.run(
        app,
        host=config.web.host,
        port=config.web.port,
        reload=False
    )


async def calculate_scores():
    """Calculate daily scores for all agents."""
    print("🧮 Calculating daily scores...")
    
    await init_database()
    scoring_engine = get_scoring_engine()
    
    results = await scoring_engine.update_all_daily_scores()
    
    print(f"✅ Processed scores for {len(results)} agents:")
    for result in results:
        agent = result["agent"]
        scores = result["scores"]
        print(f"  {agent['name']}: {scores['total_score']:.1f} pts "
              f"(Discord: {scores['discord_score']:.1f}, "
              f"GitHub: {scores['github_score']:.1f})")


async def setup_agents():
    """Set up agents from configuration."""
    print("👥 Setting up agents...")
    
    await init_database()
    db = await get_db()
    config = get_config()
    
    for agent_config in config.agents:
        agent_id = await db.upsert_agent(
            name=agent_config.name,
            discord_id=agent_config.discord_id,
            github_username=agent_config.github_username
        )
        print(f"  ✅ {agent_config.name} (ID: {agent_id})")
    
    print(f"✅ Set up {len(config.agents)} agents")


async def run_all():
    """Run both Discord bot and web dashboard."""
    print("🚀 Starting all services...")
    
    # Initialize database and agents first
    await init_database()
    await setup_agents()
    
    # Start Discord bot and web server concurrently
    await asyncio.gather(
        run_discord_bot(),
        run_web()
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Agent Analytics Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py --init                 # Initialize database
  python run.py --discord              # Run Discord bot only
  python run.py --web                  # Run web dashboard only
  python run.py --all                  # Run both services
  python run.py --calculate-scores     # Calculate daily scores
  python run.py --setup-agents         # Set up agents from config
        """
    )
    
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)"
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--init", action="store_true", help="Initialize database only")
    group.add_argument("--discord", action="store_true", help="Run Discord bot only")
    group.add_argument("--web", action="store_true", help="Run web dashboard only")
    group.add_argument("--all", action="store_true", help="Run all services")
    group.add_argument("--calculate-scores", action="store_true", help="Calculate daily scores")
    group.add_argument("--setup-agents", action="store_true", help="Set up agents from config")
    
    args = parser.parse_args()
    
    # Check if config file exists
    if not Path(args.config).exists():
        print(f"❌ Configuration file not found: {args.config}")
        print("Please create a config.yaml file based on config.yaml.example")
        sys.exit(1)
    
    # Load configuration
    try:
        config = load_config(args.config)
        set_config(config)
        print(f"✅ Loaded configuration from {args.config}")
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        sys.exit(1)
    
    # Create data directory
    Path("data").mkdir(exist_ok=True)
    
    # Run the requested operation
    try:
        if args.init:
            asyncio.run(init_database())
        elif args.setup_agents:
            asyncio.run(setup_agents())
        elif args.calculate_scores:
            asyncio.run(calculate_scores())
        elif args.discord:
            asyncio.run(run_discord())
        elif args.web:
            asyncio.run(run_web())
        elif args.all:
            asyncio.run(run_all())
            
    except KeyboardInterrupt:
        print("\n👋 Shutting down gracefully...")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()