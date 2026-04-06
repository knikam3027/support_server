import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))


async def summarize_incident(ticket_text: str, log_errors: list[str] = None) -> str:
    """Generate a concise human-readable incident summary."""
    log_section = ""
    if log_errors:
        log_section = f"\n\nExtracted log errors:\n" + "\n".join(f"- {e}" for e in log_errors[:15])

    prompt = f"""You are an IT incident analyst. Summarize this incident in 1-2 clear sentences.
Focus on: what is failing, the likely impact, and any obvious cause from the logs.

Ticket text:
{ticket_text}
{log_section}

Summary:"""

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        # Fallback: simple extractive summary
        words = ticket_text.split()
        return " ".join(words[:40]) + ("..." if len(words) > 40 else "")
