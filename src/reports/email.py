"""Email delivery for weekly reports."""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, timedelta
from typing import List, Dict, Any, Optional


class EmailReporter:
    """Sends weekly reports via email (SMTP or Resend API)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.smtp_host = self.config.get("smtp_host", os.getenv("SMTP_HOST", "smtp.resend.com"))
        self.smtp_port = int(self.config.get("smtp_port", os.getenv("SMTP_PORT", "587")))
        self.smtp_user = self.config.get("smtp_user", os.getenv("SMTP_USER", "resend"))
        self.smtp_password = self.config.get("smtp_password", os.getenv("SMTP_PASSWORD", os.getenv("RESEND_API_KEY", "")))
        self.from_email = self.config.get("from_email", os.getenv("EMAIL_FROM", "analytics@yourdomain.com"))
        self.recipients = self.config.get("recipients", [])

        # Parse EMAIL_RECIPIENTS env var if no config recipients
        if not self.recipients:
            env_recipients = os.getenv("EMAIL_RECIPIENTS", "")
            if env_recipients:
                self.recipients = [r.strip() for r in env_recipients.split(",") if r.strip()]

    @property
    def enabled(self) -> bool:
        return bool(self.smtp_password and self.recipients)

    def build_weekly_html(self, leaderboard: List[Dict[str, Any]],
                          activity_stats: Dict[str, Any],
                          end_date: date) -> str:
        """Build an HTML email body from weekly report data."""
        start_date = end_date - timedelta(days=6)

        rows = ""
        for i, agent in enumerate(leaderboard[:10], 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, str(i))
            name = agent.get("name", "Unknown")
            total = agent.get("total_score", 0) or 0
            discord = agent.get("discord_score", 0) or 0
            github = agent.get("github_score", 0) or 0
            rows += (
                f"<tr>"
                f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{medal}</td>"
                f"<td style='padding:8px 12px;border-bottom:1px solid #eee;font-weight:600'>{name}</td>"
                f"<td style='padding:8px 12px;border-bottom:1px solid #eee;text-align:right'>{discord:.1f}</td>"
                f"<td style='padding:8px 12px;border-bottom:1px solid #eee;text-align:right'>{github:.1f}</td>"
                f"<td style='padding:8px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:700;color:#27ae60'>{total:.1f}</td>"
                f"</tr>"
            )

        discord_stats = activity_stats.get("discord", {})
        github_stats = activity_stats.get("github", {})
        total_msgs = discord_stats.get("total_messages", 0)
        total_commits = github_stats.get("commits", 0)
        total_prs = github_stats.get("prs", 0)
        merged_prs = github_stats.get("merged_prs", 0)

        html = f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:640px;margin:0 auto;color:#333">
            <h2 style="color:#667eea;margin-bottom:4px">Agent Analytics: Weekly Report</h2>
            <p style="color:#888;margin-top:0">{start_date.strftime('%B %d')} &ndash; {end_date.strftime('%B %d, %Y')}</p>

            <table style="width:100%;border-collapse:collapse;margin:20px 0">
                <thead>
                    <tr style="background:#f8f9fa">
                        <th style="padding:8px 12px;text-align:left">Rank</th>
                        <th style="padding:8px 12px;text-align:left">Agent</th>
                        <th style="padding:8px 12px;text-align:right">Discord</th>
                        <th style="padding:8px 12px;text-align:right">GitHub</th>
                        <th style="padding:8px 12px;text-align:right">Total</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>

            <h3 style="color:#667eea;margin-top:28px">Weekly Activity</h3>
            <ul style="line-height:1.8">
                <li>Discord: {total_msgs} messages</li>
                <li>GitHub: {total_commits} commits, {total_prs} PRs ({merged_prs} merged)</li>
            </ul>

            <p style="color:#aaa;font-size:12px;margin-top:32px">
                Sent by Agent Analytics &middot; <a href="https://github.com/JR2321/agent-analytics" style="color:#667eea">GitHub</a>
            </p>
        </div>
        """
        return html

    def build_weekly_plain(self, leaderboard: List[Dict[str, Any]],
                           activity_stats: Dict[str, Any],
                           end_date: date) -> str:
        """Build a plain-text version of the weekly report."""
        start_date = end_date - timedelta(days=6)
        lines = [
            f"Agent Analytics: Weekly Report",
            f"{start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}",
            "",
            "Leaderboard",
            "-" * 40,
        ]
        for i, agent in enumerate(leaderboard[:10], 1):
            name = agent.get("name", "Unknown")
            total = agent.get("total_score", 0) or 0
            lines.append(f"  {i}. {name} - {total:.1f} pts")

        discord_stats = activity_stats.get("discord", {})
        github_stats = activity_stats.get("github", {})
        lines += [
            "",
            "Activity",
            f"  Discord: {discord_stats.get('total_messages', 0)} messages",
            f"  GitHub: {github_stats.get('commits', 0)} commits, "
            f"{github_stats.get('prs', 0)} PRs ({github_stats.get('merged_prs', 0)} merged)",
        ]
        return "\n".join(lines)

    async def send_weekly_report(self, leaderboard: List[Dict[str, Any]],
                                  activity_stats: Dict[str, Any],
                                  end_date: date) -> bool:
        """Send the weekly report email. Returns True on success."""
        if not self.enabled:
            print("Email not configured (missing SMTP_PASSWORD/RESEND_API_KEY or EMAIL_RECIPIENTS). Skipping.")
            return False

        start_date = end_date - timedelta(days=6)
        subject = f"Agent Analytics: Weekly Report ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d')})"

        html_body = self.build_weekly_html(leaderboard, activity_stats, end_date)
        text_body = self.build_weekly_plain(leaderboard, activity_stats, end_date)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = ", ".join(self.recipients)
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, self.recipients, msg.as_string())
            print(f"Weekly report emailed to {', '.join(self.recipients)}")
            return True
        except Exception as e:
            print(f"Failed to send weekly report email: {e}")
            return False
