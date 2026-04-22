import os
import json
import logging
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

_CLASSIFY_SYSTEM = """Jesteś asystentem klasyfikującym wiadomości użytkownika.
Odpowiadaj TYLKO w formacie JSON.

Sklasyfikuj wiadomość jako jeden z typów:
- "idea": nowa myśl, pomysł, notatka, plan, coś do zapisania
- "search": pytanie o to, czy coś już jest zapisane, szukanie czegoś w historii (np. "czy mam coś o X", "pokaż pomysły o Y", "znajdź Z")
- "chat": pytanie do bota, rozmowa, komenda niezrozumiała jako pomysł lub szukanie

Format odpowiedzi:
{"type": "idea|search|chat", "query": "wyodrębnione zapytanie jeśli search, puste string w innych przypadkach"}"""

_ANALYZE_SYSTEM = """Jesteś asystentem analizującym pomysły użytkownika.
Odpowiadaj TYLKO w formacie JSON.
Twoje zadanie: zaproponuj kategorię, napisz krótkie podsumowanie (1-2 zdania), i wygeneruj 3-5 tagów.

Jeśli pasuje jedna z istniejących kategorii — użyj jej nazwy. Jeśli żadna nie pasuje — zaproponuj nową.

Format odpowiedzi:
{
  "category": "nazwa kategorii",
  "is_new_category": true/false,
  "summary": "krótkie podsumowanie 1-2 zdania",
  "tags": ["tag1", "tag2", "tag3"]
}"""

_SEARCH_SYSTEM = """Jesteś asystentem wyszukującym pomysły.
Zwróć TYLKO JSON z listą ID pomysłów pasujących do zapytania, posortowanych od najbardziej do najmniej pasującego.
Analizuj treść, podsumowanie i tagi semantycznie.
Format: {"matching_ids": [1, 2, 3]}
Zwróć maksymalnie 10 wyników. Jeśli nic nie pasuje: {"matching_ids": []}"""

_EXPAND_SYSTEM = """Jesteś asystentem rozwijającym pomysły.
Rozwiń podany pomysł, dodaj szczegóły i zaproponuj konkretne kolejne kroki.
Pisz po polsku, strukturyzuj odpowiedź używając punktów lub sekcji.
Odpowiedź max 400 słów."""

_CHAT_SYSTEM = """Jesteś pomocnym asystentem bota do zarządzania pomysłami.
Odpowiadaj po polsku, krótko i rzeczowo.
Możesz zasugerować użytkownikowi dostępne komendy: /folders, /find, /stats, /remind, /export, /help."""


async def classify_message(content: str) -> dict:
    try:
        msg = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=100,
            system=_CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": content}],
        )
        return json.loads(msg.content[0].text)
    except Exception as e:
        logger.error(f"classify_message error: {e}")
        return {"type": "idea", "query": ""}


async def analyze_idea(content: str, existing_categories: list[str]) -> dict:
    cats_str = ", ".join(existing_categories) if existing_categories else "brak"
    prompt = f"Istniejące kategorie użytkownika: {cats_str}\n\nPomysł do analizy:\n{content}"
    try:
        msg = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=300,
            system=_ANALYZE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return json.loads(msg.content[0].text)
    except Exception as e:
        logger.error(f"analyze_idea error: {e}")
        return {
            "category": "do_kategoryzacji",
            "is_new_category": True,
            "summary": content[:100],
            "tags": ["do_kategoryzacji"],
        }


async def search_ideas(query: str, ideas_data: list[dict]) -> list[int]:
    if not ideas_data:
        return []
    ideas_json = json.dumps(ideas_data, ensure_ascii=False)
    prompt = f"Zapytanie: {query}\n\nPomysły (JSON):\n{ideas_json}"
    try:
        msg = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=200,
            system=_SEARCH_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        result = json.loads(msg.content[0].text)
        return result.get("matching_ids", [])
    except Exception as e:
        logger.error(f"search_ideas error: {e}")
        return []


async def expand_idea(content: str, summary: str) -> str:
    prompt = f"Pomysł:\n{content}\n\nPodsumowanie AI:\n{summary}"
    try:
        msg = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=600,
            system=_EXPAND_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        logger.error(f"expand_idea error: {e}")
        return "Przepraszam, nie udało się rozwinąć pomysłu. Spróbuj ponownie."


async def chat_response(message: str) -> str:
    try:
        msg = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=300,
            system=_CHAT_SYSTEM,
            messages=[{"role": "user", "content": message}],
        )
        return msg.content[0].text
    except Exception as e:
        logger.error(f"chat_response error: {e}")
        return "Przepraszam, mam teraz problem z połączeniem. Spróbuj ponownie za chwilę."


async def generate_report_insights(ideas: list[dict], period: str) -> str:
    if not ideas:
        return ""
    ideas_text = "\n".join(
        f"- {i['content'][:80]} [kategoria: {i.get('category', 'brak')}]" for i in ideas
    )
    prompt = f"Pomysły z okresu {period}:\n{ideas_text}\n\nNapisz krótki insight (2-3 zdania) o tych pomysłach."
    try:
        msg = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=200,
            system="Jesteś analitykiem krótko podsumowującym trendy w pomysłach. Pisz po polsku.",
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        logger.error(f"generate_report_insights error: {e}")
        return ""
