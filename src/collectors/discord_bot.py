"""Discord bot for collecting agent activity and posting digests."""
import asyncio
import re
from datetime import datetime, time, date, timedelta
from typing import Optional, Set, List, Dict, Any
import discord
from discord.ext import commands, tasks

from ..config import get_config
from ..database import get_db
from ..scoring import get_scoring_engine
from ..reports.daily import DailyReportGenerator
from ..reports.weekly import WeeklyReportGenerator


class AgentAnalyticsBot(commands.Bot):
    """Discord bot for tracking agent activity and posting reports."""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        intents.guilds = True
        
        super().__init__(command_prefix='!analytics', intents=intents)
        self.config = get_config()
        self.db = None
        self.scoring_engine = get_scoring_engine()
        self.daily_report_generator = DailyReportGenerator()
        self.weekly_report_generator = WeeklyReportGenerator()
        
        # Track agent user IDs for quick lookup
        self.agent_user_ids: Set[int] = set()
        self.agent_lookup: Dict[int, Dict[str, Any]] = {}
        
    async def setup_hook(self):
        """Initialize bot resources."""
        self.db = await get_db()
        await self._load_agents()
        
        # Schedule daily digest
        self.daily_digest_task.start()
        self.weekly_digest_task.start()
    
    async def _load_agents(self):
        """Load agent configurations and update database."""
        for agent_config in self.config.agents:
            discord_id = None
            if agent_config.discord_id:
                try:
                    discord_id = str(int(agent_config.discord_id))
                except ValueError:
                    continue
            
            # Upsert agent in database
            agent_id = await self.db.upsert_agent(
                name=agent_config.name,
                discord_id=discord_id,
                github_username=agent_config.github_username
            )
            
            if discord_id:
                user_id = int(discord_id)
                self.agent_user_ids.add(user_id)
                self.agent_lookup[user_id] = {
                    "id": agent_id,
                    "name": agent_config.name,
                    "discord_id": discord_id,
                    "github_username": agent_config.github_username
                }
        
        # Also check for agents with the configured role
        if self.config.discord.agent_role:
            for guild in self.guilds:
                try:
                    role = discord.utils.get(guild.roles, name=self.config.discord.agent_role)
                    if role:
                        for member in role.members:
                            if member.id not in self.agent_lookup:
                                # Create agent record for role-based agent
                                agent_id = await self.db.upsert_agent(
                                    name=member.display_name or member.name,
                                    discord_id=str(member.id)
                                )
                                
                                self.agent_user_ids.add(member.id)
                                self.agent_lookup[member.id] = {
                                    "id": agent_id,
                                    "name": member.display_name or member.name,
                                    "discord_id": str(member.id),
                                    "github_username": None
                                }
                except Exception as e:
                    print(f"Error loading role members from {guild.name}: {e}")
    
    async def on_ready(self):
        """Called when the bot is ready."""
        print(f'{self.user} has connected to Discord!')
        await self._load_agents()
        print(f'Tracking {len(self.agent_user_ids)} agents')
    
    async def on_message(self, message: discord.Message):
        """Handle incoming messages."""
        # Skip messages from the bot itself
        if message.author == self.user:
            return
        
        # Skip DMs and non-guild messages
        if not message.guild:
            return
        
        # Check if message is from a tracked agent
        if message.author.id not in self.agent_user_ids:
            return
        
        # Skip if guild filtering is enabled and this guild isn't tracked
        if self.config.discord.guilds and message.guild.id not in self.config.discord.guilds:
            return
        
        await self._process_agent_message(message)
    
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Handle reaction additions to update scores."""
        message = reaction.message
        
        # Only care about reactions on agent messages
        if message.author.id not in self.agent_user_ids:
            return
        
        # Update reaction count in database
        try:
            # Get total reactions on this message
            total_reactions = sum(r.count for r in message.reactions)
            
            async with self.db.aiosqlite.connect(self.db.db_path) as db:
                await db.execute("""
                    UPDATE discord_activity 
                    SET reactions_received = ?
                    WHERE message_id = ?
                """, (total_reactions, str(message.id)))
                await db.commit()
        except Exception as e:
            print(f"Error updating reaction count: {e}")
    
    async def _process_agent_message(self, message: discord.Message):
        """Process and store agent message activity."""
        agent_data = self.agent_lookup.get(message.author.id)
        if not agent_data:
            return
        
        # Analyze message content
        has_code = bool(re.search(r'```|`[^`]+`', message.content))
        has_media = bool(message.attachments)
        message_length = len(message.content)
        
        # Check if this is a reply
        reply_to_agent = False
        reply_to_human = False
        
        if message.reference and message.reference.message_id:
            try:
                referenced_msg = await message.channel.fetch_message(message.reference.message_id)
                if referenced_msg.author.id in self.agent_user_ids:
                    reply_to_agent = True
                else:
                    reply_to_human = True
            except:
                pass
        
        # Get current reactions
        reactions_received = sum(r.count for r in message.reactions)
        
        # Store in database
        try:
            await self.db.add_discord_activity(
                agent_id=agent_data["id"],
                channel_id=str(message.channel.id),
                channel_name=getattr(message.channel, 'name', 'DM'),
                guild_id=str(message.guild.id),
                message_id=str(message.id),
                message_length=message_length,
                has_code=has_code,
                has_media=has_media,
                reply_to_agent=reply_to_agent,
                reply_to_human=reply_to_human,
                reactions_received=reactions_received,
                timestamp=message.created_at
            )
        except Exception as e:
            print(f"Error storing Discord activity: {e}")
    
    @tasks.loop(time=time.fromisoformat(get_config().discord.digest_time))
    async def daily_digest_task(self):
        """Post daily digest."""
        try:
            # Calculate scores for yesterday (since we're running in the morning)
            yesterday = date.today() - timedelta(days=1)
            await self.scoring_engine.update_all_daily_scores(yesterday)
            
            # Generate report
            embed = await self.daily_report_generator.generate_embed(yesterday)
            
            # Find digest channel and post
            await self._post_to_digest_channel(embed)
            
        except Exception as e:
            print(f"Error in daily digest task: {e}")
    
    @tasks.loop(time=time(16, 0))  # Monday at 16:00 UTC
    async def weekly_digest_task(self):
        """Post weekly digest on Mondays."""
        if datetime.now().weekday() != 0:  # Not Monday
            return
        
        try:
            # Calculate scores for the past week
            end_date = date.today() - timedelta(days=1)
            start_date = end_date - timedelta(days=6)
            
            for day_offset in range(7):
                target_date = start_date + timedelta(days=day_offset)
                await self.scoring_engine.update_all_daily_scores(target_date)
            
            # Generate weekly report
            embed = await self.weekly_report_generator.generate_embed(end_date)
            
            # Post to digest channel
            await self._post_to_digest_channel(embed)
            
        except Exception as e:
            print(f"Error in weekly digest task: {e}")
    
    async def _post_to_digest_channel(self, embed: discord.Embed):
        """Post embed to the configured digest channel."""
        channel_name = self.config.discord.digest_channel
        
        for guild in self.guilds:
            channel = discord.utils.get(guild.channels, name=channel_name)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(embed=embed)
                    print(f"Posted digest to #{channel_name} in {guild.name}")
                    return
                except Exception as e:
                    print(f"Error posting to #{channel_name} in {guild.name}: {e}")
        
        print(f"Could not find digest channel: #{channel_name}")
    
    @commands.command(name='status')
    async def status_command(self, ctx):
        """Show bot status and tracked agents."""
        embed = discord.Embed(
            title="📊 Agent Analytics Bot Status",
            color=0x00ff00,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="Tracked Agents",
            value=f"{len(self.agent_user_ids)} agents",
            inline=True
        )
        
        embed.add_field(
            name="Guilds",
            value=f"{len(self.guilds)} guilds",
            inline=True
        )
        
        embed.add_field(
            name="Next Daily Digest",
            value=f"{self.config.discord.digest_time} UTC",
            inline=True
        )
        
        # List tracked agents
        if self.agent_lookup:
            agent_list = []
            for user_id, agent_data in list(self.agent_lookup.items())[:10]:  # Limit to first 10
                user = self.get_user(user_id)
                name = user.display_name if user else agent_data["name"]
                agent_list.append(f"• {name}")
            
            if len(self.agent_lookup) > 10:
                agent_list.append(f"... and {len(self.agent_lookup) - 10} more")
            
            embed.add_field(
                name="Tracked Agents",
                value="\n".join(agent_list),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='scores')
    async def scores_command(self, ctx, period: str = "day"):
        """Show current leaderboard."""
        if period not in ["day", "week", "month"]:
            await ctx.send("Period must be 'day', 'week', or 'month'")
            return
        
        try:
            leaderboard = await self.db.get_leaderboard(period=period, limit=10)
            
            embed = discord.Embed(
                title=f"🏆 Agent Leaderboard ({period.title()})",
                color=0x00ff00,
                timestamp=datetime.utcnow()
            )
            
            if not leaderboard:
                embed.description = "No activity data available."
            else:
                leaderboard_text = []
                for i, agent in enumerate(leaderboard, 1):
                    emoji = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
                    score = agent.get('total_score', 0) or 0
                    leaderboard_text.append(f"{emoji} {agent['name']} - {score:.1f} pts")
                
                embed.description = "\n".join(leaderboard_text)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"Error generating leaderboard: {e}")


async def run_discord_bot():
    """Run the Discord bot."""
    config = get_config()
    bot = AgentAnalyticsBot()
    
    try:
        await bot.start(config.discord.token)
    except Exception as e:
        print(f"Error starting Discord bot: {e}")
    finally:
        await bot.close()