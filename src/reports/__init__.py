"""Report generators for daily and weekly digests."""

from .daily import DailyReportGenerator
from .weekly import WeeklyReportGenerator

__all__ = [
    "DailyReportGenerator",
    "WeeklyReportGenerator"
]