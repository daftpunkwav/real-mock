"""Site allowlist for resume-market web search.

Responsibilities:
- Optional ``site:`` filter list used when an Agent sets force_job_boards
- Human labels for logs

Empty list is allowed (open-web search only). This module must not import
FastAPI, ORM, or the search client.
"""

from __future__ import annotations

RESUME_MARKET_SEARCH_SITES: list[str] = [
    "nowcoder.com",
    "zhipin.com",
    "liepin.com",
    "lagou.com",
    "linkedin.com",
    "51job.com",
    "yingjiesheng.com",
    "indeed.com",
    "glassdoor.com",
    "levels.fyi",
    "maimai.cn",
    "kanzhun.com",
    "jobui.com",
    "juejin.cn",
    "infoq.cn",
    "stackoverflow.com",
]

RESUME_MARKET_SITE_LABELS: dict[str, str] = {
    "nowcoder.com": "Nowcoder",
    "zhipin.com": "BOSS Zhipin",
    "liepin.com": "Liepin",
    "lagou.com": "Lagou",
    "linkedin.com": "LinkedIn",
    "51job.com": "51Job",
    "yingjiesheng.com": "Yingjiesheng",
    "indeed.com": "Indeed",
    "glassdoor.com": "Glassdoor",
    "levels.fyi": "Levels.fyi",
    "maimai.cn": "Maimai",
    "kanzhun.com": "Kanzhun",
    "jobui.com": "JobUI",
    "juejin.cn": "Juejin",
    "infoq.cn": "InfoQ China",
    "stackoverflow.com": "Stack Overflow",
}
