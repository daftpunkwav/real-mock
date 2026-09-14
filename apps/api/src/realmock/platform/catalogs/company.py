"""Company interview-style catalog (read-only shared data).

Shared by interview / prep: style, focus areas, sample questions.
No DB / LLM / HTTP.
"""

from __future__ import annotations

from realmock.platform.schemas import CompanyInfo

BUILTIN_COMPANIES: list[dict] = [
    {
        "id": "bytedance",
        "name": "ByteDance",
        "style": "High-frequency probing, strong project deep-dives, business thinking and quantified impact",
        "focus_areas": [
            "Project deep dive",
            "Business thinking",
            "Performance optimization",
            "System design",
            "Algorithms",
        ],
        "sample_questions": [
            "You mentioned optimizing API performance — what were the QPS numbers before and after?",
            "What business value does this approach deliver, and how do you measure success?",
            "If traffic grew 10x, how would your architecture scale?",
        ],
        "interview_flow": "Self intro → Project deep dive (40%) → Fundamentals → System design → Your questions",
        "pressure_level": "High",
    },
    {
        "id": "tencent",
        "name": "Tencent",
        "style": "Solid fundamentals, project experience, teamwork and incident handling",
        "focus_areas": [
            "Fundamentals",
            "Project experience",
            "Teamwork",
            "Incident handling",
            "Code quality",
        ],
        "sample_questions": [
            "If a major production incident happens, how do you locate and resolve it?",
            "Describe a time you disagreed with a teammate on a technical decision and how you resolved it.",
            "Explain the difference between TCP and UDP.",
        ],
        "interview_flow": "Self intro → Fundamentals → Project experience → Scenarios → Your questions",
        "pressure_level": "Medium",
    },
    {
        "id": "alibaba",
        "name": "Alibaba",
        "style": "Business thinking, technical depth, and values fit",
        "focus_areas": [
            "Business thinking",
            "Technical depth",
            "Distributed systems",
            "High concurrency",
            "Values",
        ],
        "sample_questions": [
            "How do you understand the core pain point of this business scenario?",
            "Design a flash-sale system that supports tens of millions of users.",
            "Describe your most impactful project and your role in it.",
        ],
        "interview_flow": "Self intro → Project experience → Technical deep dive → System design → Values → Your questions",
        "pressure_level": "Medium-High",
    },
    {
        "id": "meituan",
        "name": "Meituan",
        "style": "Engineering ability, business delivery, and problem solving",
        "focus_areas": [
            "Engineering practice",
            "Business delivery",
            "Performance optimization",
            "Data-driven decisions",
        ],
        "sample_questions": [
            "How do you use data to drive technical decisions?",
            "Describe a project you took from 0 to 1.",
        ],
        "interview_flow": "Self intro → Projects → Technical → Business scenarios → Your questions",
        "pressure_level": "Medium",
    },
    {
        "id": "mihoyo",
        "name": "miHoYo",
        "style": "Project experience, engine understanding, performance, and game-dev passion",
        "focus_areas": [
            "Game engines",
            "Performance optimization",
            "Rendering pipeline",
            "Project experience",
            "GC / memory",
        ],
        "sample_questions": [
            "How would you investigate stuttering caused by GC in Unity?",
            "Describe the hardest technical problem in a game project you worked on.",
            "How do you reduce Draw Call count?",
        ],
        "interview_flow": "Self intro → Project deep dive → Engine / graphics → Algorithms → Your questions",
        "pressure_level": "Medium-High",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "style": "Technical depth, research ability, system design, and AI/ML expertise",
        "focus_areas": [
            "Machine learning",
            "System design",
            "Coding ability",
            "Research mindset",
            "Engineering practice",
        ],
        "sample_questions": [
            "Design a distributed training system for large language models.",
            "How would you debug a model that performs well on training but poorly in production?",
        ],
        "interview_flow": "Self intro → Technical deep dive → Coding → System design → Your questions",
        "pressure_level": "High",
    },
    {
        "id": "google",
        "name": "Google",
        "style": "Algorithms, system design, leadership, and Googleyness",
        "focus_areas": [
            "Algorithms",
            "System design",
            "Code quality",
            "Leadership",
            "Innovation",
        ],
        "sample_questions": [
            "Design Google Maps routing algorithm at scale.",
            "Tell me about a time you had to make a difficult technical trade-off.",
        ],
        "interview_flow": "Self intro → Coding → System design → Behavioral → Your questions",
        "pressure_level": "High",
    },
]


def get_all_companies() -> list[CompanyInfo]:
    """Return all built-in companies as shared ``CompanyInfo`` contracts."""
    companies = []
    for c in BUILTIN_COMPANIES:
        companies.append(
            CompanyInfo(
                id=c["id"],
                name=c["name"],
                style=c["style"],
                focus_areas=c["focus_areas"],
                sample_questions=c["sample_questions"],
                interview_flow=c["interview_flow"],
                pressure_level=c["pressure_level"],
            )
        )
    return companies


def get_company_by_id(company_id: str) -> dict | None:
    """Look up a company raw dict by id or display name."""
    for c in BUILTIN_COMPANIES:
        if c["id"] == company_id or c["name"] == company_id:
            return c
    return None


def get_company_context(company_id: str) -> str:
    """Build English company interview-style context for agents."""
    company = get_company_by_id(company_id)
    if not company:
        return (
            "General technical interview style: fundamentals, project experience, "
            "and technical depth."
        )

    questions = "\n".join(f"- {q}" for q in company["sample_questions"])
    return f"""## Target company: {company['name']}
Interview style: {company['style']}
Focus areas: {', '.join(company['focus_areas'])}
Typical interview flow: {company['interview_flow']}
Pressure level: {company['pressure_level']}
Sample question style:
{questions}"""
