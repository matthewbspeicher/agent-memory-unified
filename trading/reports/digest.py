from datetime import datetime, timezone
import aiosqlite
import logging

logger = logging.getLogger(__name__)


class DigestGenerator:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def generate_daily_digest(self) -> str:
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_str = today.isoformat()

        cursor = await self._db.execute(
            """SELECT agent_name, COUNT(*) as count, 
               SUM(CASE WHEN status='executed' THEN 1 ELSE 0 END) as executed_count 
               FROM opportunities WHERE created_at >= ? GROUP BY agent_name""",
            (today_str,),
        )
        opp_stats = await cursor.fetchall()

        cursor = await self._db.execute(
            "SELECT event_type, COUNT(*) as count FROM risk_events WHERE created_at >= ? GROUP BY event_type",
            (today_str,),
        )
        risk_stats = await cursor.fetchall()

        cursor = await self._db.execute(
            "SELECT COUNT(*) as sum_trades FROM trades WHERE created_at >= ?",
            (today_str,),
        )
        trade_count_row = await cursor.fetchone()
        trade_count = trade_count_row["sum_trades"] if trade_count_row else 0

        html = [
            "<html><head><style>body { font-family: sans-serif; }</style></head><body>",
            f"<h1>Daily Trading Digest - {today.strftime('%Y-%m-%d')}</h1>",
            "<h2>Opportunities per Agent</h2>",
            "<ul>",
        ]

        if not opp_stats:
            html.append("<li>No opportunities generated today.</li>")
        else:
            for row in opp_stats:
                html.append(
                    f"<li><b>{row['agent_name']}</b>: {row['count']} generated, {row['executed_count']} executed</li>"
                )
        html.append("</ul>")

        html.append(f"<h2>Total Trades Today: {trade_count}</h2>")

        html.append("<h2>Risk Events</h2>")
        if not risk_stats:
            html.append("<p>No risk events triggered today.</p>")
        else:
            html.append("<ul>")
            for row in risk_stats:
                html.append(
                    f"<li><b>{row['event_type']}</b>: {row['count']} events</li>"
                )
            html.append("</ul>")

        html.append("</body></html>")

        digest_html = "\n".join(html)
        logger.info("Generated daily digest HTML report.")
        return digest_html
