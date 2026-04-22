# IdeaBot — Inteligentny bot Telegram do zarządzania pomysłami

Bot działa w **dwóch miejscach jednocześnie**:
- 💬 **Prywatny chat** — wpisujesz pomysły, przeglądasz, wyszukujesz
- 🗂️ **Prywatna grupa z Topics** — każda kategoria = osobny temat (Topic) w grupie

---

## Wymagania wstępne

- [Docker](https://docs.docker.com/get-docker/) + [Docker Compose](https://docs.docker.com/compose/install/)
- Konto Telegram + Bot Token
- Klucz API Anthropic

---

## Konfiguracja krok po kroku

### 1. Utwórz bota przez BotFather

1. Otwórz Telegram → `@BotFather` → `/newbot`
2. Podaj nazwę i username (musi kończyć się na `bot`)
3. Skopiuj token do `.env` jako `TELEGRAM_BOT_TOKEN`

### 2. Utwórz prywatną grupę z Topics

1. W Telegramie utwórz nową grupę (prywatną)
2. Wejdź w ustawienia grupy → *Zarządzaj grupą* → *Tematy* → włącz
   *(Wymaga Supergrupy — Telegram sam zaproponuje upgrade)*
3. Dodaj bota do grupy
4. Ustaw bota jako **administratora** z uprawnieniami:
   - ✅ Zarządzaj tematami (Manage Topics)
   - ✅ Wysyłaj wiadomości

### 3. Znajdź GROUP_CHAT_ID

**Sposób 1 — przez @userinfobot:**
Dodaj `@userinfobot` do grupy, napisz cokolwiek — zwróci ID grupy (np. `-1001234567890`).

**Sposób 2 — przez API:**
```
https://api.telegram.org/bot<TOKEN>/getUpdates
```
Wyślij wiadomość na grupę, znajdź `"chat": {"id": -1001234567890}`.

### 4. Konfiguracja .env

```bash
cp .env.example .env
```

Uzupełnij `.env`:

```env
TELEGRAM_BOT_TOKEN=twoj_token
ANTHROPIC_API_KEY=twoj_klucz_anthropic
ADMIN_TELEGRAM_ID=twoje_telegram_id      # uzyskaj przez @userinfobot
GROUP_CHAT_ID=-1001234567890             # ID grupy z Topics
POSTGRES_PASSWORD=silne_haslo
```

### 5. Uruchomienie

```bash
docker-compose up -d
```

Bot automatycznie czeka na gotowość bazy i sprawdza dostęp do grupy.

### 6. Pierwszy kod zaproszenia

```bash
docker-compose exec bot python seed.py
```

Lub wyślij `/gen_invite` do bota (tylko admin).

---

## Jak to działa

```
Piszesz pomysł w prywatnym chacie
        ↓
Claude AI analizuje (kategoria, podsumowanie, tagi)
        ↓
Potwierdzasz przez inline buttons
        ↓
Zapisuje do PostgreSQL
        +
Publikuje do odpowiedniego Topicu w grupie
(tworzy nowy Topic jeśli kategoria jest nowa)
```

---

## Komendy użytkownika

| Komenda | Opis |
|---------|------|
| `/start CODE` | Rejestracja z kodem zaproszenia |
| `/help` | Lista komend |
| `/folders` | Przeglądaj kategorie i pomysły |
| `/find [zapytanie]` | Wyszukaj pomysły |
| `/stats` | Twoje statystyki |
| `/remind` | Skonfiguruj przypomnienia i raporty |
| `/export` | Eksportuj pomysły (TXT lub JSON) |
| `/delete_account` | Usuń konto i wszystkie dane |

## Komendy admina

| Komenda | Opis |
|---------|------|
| `/gen_invite` | Jednorazowy kod zaproszenia |
| `/gen_invite 5` | Kod na 5 użyć |
| `/list_invites` | Lista aktywnych kodów |
| `/users` | Lista użytkowników |
| `/ban [id]` | Zablokuj użytkownika |
| `/unban [id]` | Odblokuj użytkownika |

---

## Zarządzanie

```bash
# Logi w czasie rzeczywistym
docker-compose logs -f bot

# Restart bota
docker-compose restart bot

# Zatrzymanie
docker-compose down

# Backup bazy danych
docker-compose exec db pg_dump -U user ideabot > backup_$(date +%Y%m%d).sql

# Przywrócenie backupu
cat backup.sql | docker-compose exec -T db psql -U user ideabot

# Migracje
docker-compose exec bot alembic upgrade head
```

---

## Przykład użycia

```
Ty: Aplikacja mobilna z AI do śledzenia nawyków

Bot: 💡 Twój pomysł został przeanalizowany!
     📁 Proponowana kategoria: Aplikacje
     📝 Podsumowanie: Aplikacja mobilna z AI...
     🏷️ Tagi: #aplikacja #AI #nawyki
     [✅ Tak, zapisz] [✏️ Zmień] [➕ Nowa]

(po kliknięciu "Tak, zapisz")

Bot: ✅ Zapisano!
     🔗 Opublikowano w grupie → kategoria Aplikacje
     Chcesz żebym rozwinął ten pomysł?
     [✅ Tak] [❌ Nie] [🔗 Otwórz w grupie]
```

W grupie automatycznie pojawia się wiadomość w Topicu "Aplikacje".

---

## Architektura

```
Telegram (prywatny chat + grupa z Topics)
         ↕
python-telegram-bot 21.x (async)
         ↕
Handlers → Services (AI + Group + Scheduler)
         ↕
PostgreSQL (SQLAlchemy async + Alembic)
```
