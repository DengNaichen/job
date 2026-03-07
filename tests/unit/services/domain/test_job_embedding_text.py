from __future__ import annotations

from app.services.domain.job_embedding_text import build_job_embedding_text


def test_build_job_embedding_text_keeps_signal_and_drops_obvious_noise() -> None:
    text = build_job_embedding_text(
        title="Senior Backend Engineer, Fraud Platform",
        description="""
About Acme Pay
Acme Pay builds the financial infrastructure used by millions of businesses around the world.

The Role
You will join the Fraud Platform team to build backend systems that detect account abuse.

What you'll do
- Build Python and Go services that power fraud detection workflows.
- Design APIs and event-driven pipelines using PostgreSQL, Kafka, and Redis.

Qualifications
- 5+ years of backend software engineering experience.
- Strong experience with Python, distributed systems, SQL, and cloud infrastructure.

Benefits
- Medical, dental, and vision coverage.

Work Authorization
Acme Pay is unable to provide visa sponsorship for this role at this time.

EEO Statement
Acme Pay is an equal opportunity employer.

How to apply
Please submit your application through our careers site.
""",
        structured_jd={
            "required_skills": [
                "Python (computer programming)",
                "Go (computer programming)",
                "PostgreSQL",
            ],
            "job_domain_normalized": "cybersecurity",
            "seniority_level": "senior",
        },
    )

    assert "Title: Senior Backend Engineer, Fraud Platform" in text
    assert "Domain: cybersecurity" in text
    assert "Seniority: senior" in text
    assert "Required skills: Python (computer programming), Go (computer programming), PostgreSQL" in text
    assert "Build Python and Go services" in text
    assert "Strong experience with Python" in text
    assert "Acme Pay builds the financial infrastructure" not in text
    assert "visa sponsorship" not in text.lower()
    assert "equal opportunity employer" not in text.lower()
    assert "careers site" not in text.lower()


def test_build_job_embedding_text_treats_about_you_as_requirements() -> None:
    text = build_job_embedding_text(
        title="Senior Account Manager",
        description="""
About 9fin
9fin is the AI platform powering global debt markets.

WHAT YOU'LL WORK ON
- Managing and building strong relationships across a book of key clients
- Driving account expansion across existing accounts

ABOUT YOU
- Minimum 6 years of relevant account management experience
- Strong knowledge of financial markets
""",
        structured_jd={"seniority_level": "manager"},
    )

    assert "Managing and building strong relationships" in text
    assert "Minimum 6 years of relevant account management experience" in text
    assert "Strong knowledge of financial markets" in text
    assert "9fin is the AI platform powering global debt markets" not in text


def test_build_job_embedding_text_falls_back_to_body_when_no_headings_exist() -> None:
    text = build_job_embedding_text(
        title="Backend Engineer",
        description="Build resilient pipelines for product teams.",
        structured_jd=None,
    )

    assert "Title: Backend Engineer" in text
    assert "Additional role context:" in text
    assert "Build resilient pipelines for product teams." in text
