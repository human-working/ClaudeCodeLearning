"""Single source of truth for the consultancy packages.

The frontend renders this list via GET /api/packages, and the matcher puts the same
data in Claude's system prompt, so prices and features can never drift apart.
"""
import os

CURRENCY = os.getenv("CURRENCY", "USD")

PACKAGES = [
    {
        "id": "foundation",
        "name": "AI Foundation",
        "price_per_month": 1999,
        "tagline": "Get started with AI the right way.",
        "best_for": "Small teams exploring their first AI use cases.",
        "features": [
            "AI readiness assessment and opportunity map",
            "1 prioritised use case scoped per quarter",
            "8 consultant hours per month",
            "Monthly 60-minute strategy call",
            "Prompt-engineering and AI-tooling playbook",
            "Email support (2 business-day response)",
        ],
    },
    {
        "id": "accelerate",
        "name": "AI Accelerate",
        "price_per_month": 4999,
        "tagline": "Ship production AI features with expert help.",
        "best_for": "Growing companies building AI into products or operations.",
        "features": [
            "Everything in AI Foundation",
            "24 consultant hours per month",
            "Proof-of-concept build for up to 2 use cases per quarter",
            "LLM / RAG architecture and model-selection reviews",
            "Data-readiness and evaluation-pipeline setup",
            "Bi-weekly working sessions with your engineers",
            "Priority support (1 business-day response)",
        ],
    },
    {
        "id": "transform",
        "name": "AI Transform",
        "price_per_month": 9999,
        "tagline": "An embedded AI partner for organisation-wide change.",
        "best_for": "Enterprises scaling AI across departments with governance needs.",
        "features": [
            "Everything in AI Accelerate",
            "60 consultant hours per month and a dedicated lead consultant",
            "AI governance, risk and compliance framework (e.g. EU AI Act, ISO 42001)",
            "Security and privacy review of AI systems",
            "Change management and team training programme",
            "Quarterly executive roadmap review with KPIs",
            "Same-day support with a 4-hour SLA",
        ],
    },
]

PACKAGE_IDS = tuple(p["id"] for p in PACKAGES)


def catalogue_text() -> str:
    lines = []
    for p in PACKAGES:
        lines.append(
            f"- id={p['id']} | {p['name']} | {p['price_per_month']:,} {CURRENCY}/month | "
            f"best for: {p['best_for']}\n  features: " + "; ".join(p["features"])
        )
    return "\n".join(lines)
