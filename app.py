import asyncio
import os
import re
import random
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from words import GOOD_WORDS, BAD_WORDS

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

print("=" * 50)
print("ЗАГРУЗКА APP.PY")
print(f"BOT_TOKEN: {'задан' if BOT_TOKEN else 'НЕ ЗАДАН!!!'}")
print("=" * 50)

# ============================================================
# НАСТРОЙКИ
# ============================================================
AUTO_STARS_ENABLED = True
DEBUG_AUTO = True
MAX_PLUS_PER_HOUR = 3
MAX_PLUS_PER_DAY = 20
SAME_WORD_COOLDOWN_HOURS = 6
SAME_BAD_WORD_COOLDOWN_MINUTES = 1

CASINO_MIN_BET = 10
CASINO_MAX_BET = 2000
DICE_MIN_BET = 10
DICE_MAX_BET = 5000
STEAL_COOLDOWN_HOURS = 24
STEAL_MIN_BALANCE = 50
STEAL_SUCCESS_CHANCE = 0.4
STEAL_MIN_AMOUNT = 5
STEAL_MAX_AMOUNT = 20
STEAL_FAIL_PENALTY = 10

pending_duels = {}


# ============================================================
# АДМИНЫ
# ============================================================
def load_admins():
    ids = set()
    for x in os.getenv("ADMIN_IDS", "").split(","):
        x = x.strip()
        if x.isdigit():
            ids.add(int(x))
    if os.path.exists("admins.txt"):
        with open("admins.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.isdigit():
                    ids.add(int(line))
    return ids


def save_admin(uid):
    if uid in load_admins():
        return False
    with open("admins.txt", "a", encoding="utf-8") as f:
        f.write(f"\n{uid}")
    return True


def remove_admin(uid):
    if not os.path.exists("admins.txt"):
        return False
    with open("admins.txt", "r", encoding="utf-8") as f:
        lines = f.readlines()
    new = [l for l in lines if l.strip() != str(uid)]
    if len(new) == len(lines):
        return False
    with open("admins.txt", "w", encoding="utf-8") as f:
        f.writelines(new)
    return True


def is_admin(uid):
    return uid in load_admins()


# ============================================================
# СЕЗОНЫ
# ============================================================
def get_season_start(now=None):
    if now is None:
        now = datetime.now()
    days_since_friday = (now.weekday() - 4) % 7
    friday = now - timedelta(days=days_since_friday)
    return friday.replace(hour=0, minute=0, second=0, microsecond=0)


def get_season_end(now=None):
    return get_season_start(now) + timedelta(days=7)


# ============================================================
# БОТ И БАЗА
# ============================================================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

db = sqlite3.connect("dobro_stars.db")
cursor = db.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER, chat_id INTEGER, username TEXT,
        stars INTEGER DEFAULT 0,
        good_words INTEGER DEFAULT 0,
        bad_words INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, chat_id)
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER, target_id INTEGER, target_name TEXT,
        amount INTEGER, reason TEXT, created_at TEXT
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS season_stats (
        user_id INTEGER, chat_id INTEGER,
        season_start TEXT,
        won INTEGER DEFAULT 0, lost INTEGER DEFAULT 0,
        good_words INTEGER DEFAULT 0, bad_words INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, chat_id, season_start)
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS casino_stats (
        user_id INTEGER, chat_id INTEGER,
        won_total INTEGER DEFAULT 0, lost_total INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, chat_id)
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS steal_cooldowns (
        thief_id INTEGER, target_id INTEGER, chat_id INTEGER,
        last_steal TEXT,
        PRIMARY KEY (thief_id, target_id, chat_id)
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS last_weekly_report (
        chat_id INTEGER PRIMARY KEY,
        last_report TEXT
    )
""")
db.commit()


# ============================================================
# БД ФУНКЦИИ
# ============================================================
def ensure_user(uid, cid, un):
    cursor.execute("""
        INSERT INTO users (user_id, chat_id, username, stars) VALUES (?, ?, ?, 0)
        ON CONFLICT(user_id, chat_id) DO UPDATE SET username=?
    """, (uid, cid, un, un))
    db.commit()


def get_stars(uid, cid):
    cursor.execute("SELECT stars FROM users WHERE user_id=? AND chat_id=?", (uid, cid))
    r = cursor.fetchone()
    return r[0] if r else 0


def update_stars(uid, cid, un, amount):
    ensure_user(uid, cid, un)
    new = get_stars(uid, cid) + amount
    cursor.execute("UPDATE users SET stars=? WHERE user_id=? AND chat_id=?", (new, uid, cid))
    db.commit()
    return new


def add_log(cid, tid, tn, amount, reason):
    cursor.execute("""
        INSERT INTO logs (chat_id, target_id, target_name, amount, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (cid, tid, tn, amount, reason, datetime.now().isoformat()))
    db.commit()


def inc_word_stat(uid, cid, un, is_good):
    ensure_user(uid, cid, un)
    col = "good_words" if is_good else "bad_words"
    cursor.execute(f"UPDATE users SET {col} = {col} + 1 WHERE user_id=? AND chat_id=?", (uid, cid))
    db.commit()


def get_user_word_stats(uid, cid):
    cursor.execute("SELECT good_words, bad_words FROM users WHERE user_id=? AND chat_id=?", (uid, cid))
    r = cursor.fetchone()
    return r if r else (0, 0)


def update_season_stat(uid, cid, un, won=0, lost=0, good=0, bad=0):
    season = get_season_start().isoformat()
    ensure_user(uid, cid, un)
    cursor.execute("""
        INSERT INTO season_stats (user_id, chat_id, season_start) VALUES (?, ?, ?)
        ON CONFLICT(user_id, chat_id, season_start) DO NOTHING
    """, (uid, cid, season))
    cursor.execute("""
        UPDATE season_stats SET
            won = won + ?, lost = lost + ?,
            good_words = good_words + ?, bad_words = bad_words + ?
        WHERE user_id=? AND chat_id=? AND season_start=?
    """, (won, lost, good, bad, uid, cid, season))
    db.commit()


def get_season_stats(uid, cid):
    season = get_season_start().isoformat()
    cursor.execute("""
        SELECT won, lost, good_words, bad_words FROM season_stats
        WHERE user_id=? AND chat_id=? AND season_start=?
    """, (uid, cid, season))
    r = cursor.fetchone()
    return r if r else (0, 0, 0, 0)


def update_casino_stats(uid, cid, won=0, lost=0):
    cursor.execute("""
        INSERT INTO casino_stats (user_id, chat_id, won_total, lost_total)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, chat_id) DO UPDATE SET
            won_total = won_total + ?, lost_total = lost_total + ?
    """, (uid, cid, won, lost, won, lost))
    db.commit()


def get_casino_stats(uid, cid):
    cursor.execute("SELECT won_total, lost_total FROM casino_stats WHERE user_id=? AND chat_id=?", (uid, cid))
    r = cursor.fetchone()
    return r if r else (0, 0)


# ============================================================
# ПОИСК ПОЛЬЗОВАТЕЛЯ ПО @НИКУ
# ============================================================
def find_user_by_username(un, cid):
    if not un:
        return None
    un = un.lstrip("@").strip()
    if not un:
        return None
    # точное (без регистра)
    cursor.execute("""
        SELECT user_id, username FROM users
        WHERE chat_id=? AND LOWER(username)=LOWER(?)
    """, (cid, un))
    row = cursor.fetchone()
    if row:
        return row
    # точное с @
    cursor.execute("""
        SELECT user_id, username FROM users
        WHERE chat_id=? AND LOWER(username)=LOWER(?)
    """, (cid, "@" + un))
    row = cursor.fetchone()
    if row:
        return row
    # подстрока
    cursor.execute("""
        SELECT user_id, username FROM users
        WHERE chat_id=? AND LOWER(username) LIKE ?
        ORDER BY LENGTH(username) ASC LIMIT 1
    """, (cid, f"%{un.lower()}%"))
    row = cursor.fetchone()
    if row:
        return row
    return None


# ============================================================
# ЛОГИКА СЛОВ
# ============================================================
def has_word(text, word):
    t = text.lower()
    if " " in word:
        return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", t) is not None
    if len(word) <= 3:
        return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", t) is not None
    pattern = rf"(?<!\w){re.escape(word)}(а|у|ом|ем|е|ы|и|ов|ев|ам|ям|ами|ями|ах|ях|ой|ей|ою|ею)?(?!\w)"
    return re.search(pattern, t) is not None


def find_best_word(text, words_dict):
    best_w, best_v = None, 0
    for w, v in words_dict.items():
        if has_word(text, w) and v > best_v:
            best_w, best_v = w, v
    return best_w, best_v


# ============================================================
# АНТИФАРМ
# ============================================================
def plus_count_last_hour(uid, cid):
    cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
    cursor.execute("""
        SELECT COUNT(*) FROM logs WHERE target_id=? AND chat_id=?
        AND amount > 0 AND reason LIKE 'авто:%' AND created_at > ?
    """, (uid, cid, cutoff))
    return cursor.fetchone()[0]


def plus_sum_last_day(uid, cid):
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) FROM logs WHERE target_id=? AND chat_id=?
        AND amount > 0 AND reason LIKE 'авто:%' AND created_at > ?
    """, (uid, cid, cutoff))
    return cursor.fetchone()[0]


def same_word_used_recently(uid, cid, word, minutes):
    cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
    cursor.execute("""
        SELECT COUNT(*) FROM logs WHERE target_id=? AND chat_id=?
        AND reason LIKE ? AND created_at > ?
    """, (uid, cid, f"%«{word}»%", cutoff))
    return cursor.fetchone()[0] > 0
    # ============================================================
# КОМАНДЫ
# ============================================================

@dp.message(Command("start", "help", "помощь"))
async def cmd_help(m: Message):
    print(f"[CMD] /start от {m.from_user.full_name}")
    await m.answer(
        "👋 <b>Бот Добро-Звёзды</b>\n\n"
        "/профиль — профиль\n"
        "/таблица — топ\n"
        "/антитоп — топ злых\n"
        "/топ_сезона — топы за неделю\n"
        "/сезон — инфо о сезоне\n"
        "/сводка — отчёт за прошлую неделю\n"
        "/тест_авто фраза\n\n"
        "🎲 /рулетка 100 красное\n"
        "🎲 /кости @ник 100 / /принять / /отклонить\n"
        "🥷 /украсть @ник\n\n"
        "🛠 /добро N @ник причина | /зло N @ник причина\n"
        "/авто вкл|выкл | /админ | /разжаловать | /логи"
    )


@dp.message(Command("тест_авто"))
async def cmd_test(m: Message):
    p = (m.text or "").split(maxsplit=1)
    if len(p) < 2:
        await m.reply("Использование: /тест_авто любая фраза")
        return
    t = p[1]
    bw, bv = find_best_word(t, BAD_WORDS)
    gw, gv = find_best_word(t, GOOD_WORDS)
    lines = [f"🔍 <code>{t}</code>", ""]
    lines.append(f"❌ Плохое: <b>{bw}</b> (−{bv})" if bw else "❌ Плохих: нет")
    lines.append(f"✅ Хорошее: <b>{gw}</b> (+{gv})" if gw else "✅ Хороших: нет")
    if bw:
        lines.append(f"\n➡️ Итог: <b>−{bv}</b> ⭐")
    elif gw:
        lines.append(f"\n➡️ Итог: <b>+{gv}</b> ⭐")
    else:
        lines.append("\n➡️ Итог: 0")
    await m.reply("\n".join(lines))


@dp.message(Command("авто"))
async def cmd_auto(m: Message):
    global AUTO_STARS_ENABLED
    print(f"[CMD] /авто от {m.from_user.full_name}")
    if not is_admin(m.from_user.id):
        await m.reply("❌ Только админы.")
        return
    p = (m.text or "").split(maxsplit=1)
    if len(p) < 2 or p[1] not in ("вкл", "выкл"):
        await m.reply(f"Авто: <b>{'вкл' if AUTO_STARS_ENABLED else 'выкл'}</b>")
        return
    AUTO_STARS_ENABLED = (p[1] == "вкл")
    await m.reply(f"✅ Авто <b>{'включены' if AUTO_STARS_ENABLED else 'выключены'}</b>.")


@dp.message(Command("сезон"))
async def cmd_season(m: Message):
    start = get_season_start()
    end = get_season_end()
    left = end - datetime.now()
    await m.reply(
        f"📅 <b>Сезон</b>\n"
        f"Начало: <b>{start.strftime('%d.%m.%Y %H:%M')}</b>\n"
        f"Конец: <b>{end.strftime('%d.%m.%Y %H:%M')}</b>\n"
        f"Осталось: <b>{left.days}д {left.seconds//3600}ч</b>"
    )


@dp.message(Command("профиль"))
async def cmd_profile(m: Message):
    t = m.reply_to_message.from_user if m.reply_to_message else m.from_user
    s = get_stars(t.id, m.chat.id)
    gw, bw = get_user_word_stats(t.id, m.chat.id)
    cw, cl = get_casino_stats(t.id, m.chat.id)
    sw, sl, sg, sb = get_season_stats(t.id, m.chat.id)
    if s < 0:
        e = "💀"
    elif s == 0:
        e = "😐"
    elif s < 50:
        e = "🙂"
    elif s < 200:
        e = "😊"
    elif s < 500:
        e = "🌟"
    else:
        e = "👑"
    await m.reply(
        f"{e} <b>{t.full_name}</b>\n"
        f"🆔 <code>{t.id}</code>\n\n"
        f"⭐ Баланс: <b>{s}</b>\n\n"
        f"📝 Слова всего: ✅ {gw} | ❌ {bw}\n\n"
        f"🎰 Казино всего: +{cw} / −{cl}\n"
        f"📅 Сезон: 🎰 +{sw} / −{sl}, ✅ {sg} | ❌ {sb}"
    )


@dp.message(Command("таблица"))
async def cmd_top(m: Message):
    cursor.execute("""
        SELECT user_id, username, stars FROM users
        WHERE chat_id=? AND stars != 0 ORDER BY stars DESC LIMIT 10
    """, (m.chat.id,))
    rows = cursor.fetchall()
    if not rows:
        await m.reply("Пока никто не получил звёзд 🙂")
        return
    text = "🏆 <b>Топ</b>\n\n"
    for i, (uid, un, st) in enumerate(rows, start=1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        try:
            mm = await bot.get_chat_member(m.chat.id, uid)
            name = mm.user.full_name
        except Exception:
            name = un or f"ID {uid}"
        text += f"{medal} {name} — <b>{st}</b> ⭐\n"
    await m.reply(text)


@dp.message(Command("антитоп"))
async def cmd_antitop(m: Message):
    cursor.execute("""
        SELECT user_id, username, stars FROM users
        WHERE chat_id=? AND stars < 0 ORDER BY stars ASC LIMIT 10
    """, (m.chat.id,))
    rows = cursor.fetchall()
    if not rows:
        await m.reply("Пока ни у кого нет минуса 🙂")
        return
    text = "😈 <b>Антитоп</b>\n\n"
    for i, (uid, un, st) in enumerate(rows, start=1):
        try:
            mm = await bot.get_chat_member(m.chat.id, uid)
            name = mm.user.full_name
        except Exception:
            name = un or f"ID {uid}"
        text += f"{i}. {name} — <b>{st}</b> ⭐\n"
    await m.reply(text)


@dp.message(Command("топ_сезона"))
async def cmd_season_top(m: Message):
    season = get_season_start().isoformat()
    text = "📅 <b>Топы за сезон</b>\n\n"
    cursor.execute("""
        SELECT user_id, good_words FROM season_stats
        WHERE chat_id=? AND season_start=? AND good_words > 0
        ORDER BY good_words DESC LIMIT 5
    """, (m.chat.id, season))
    rows = cursor.fetchall()
    text += "✅ <b>Добрые:</b>\n"
    if rows:
        for i, (uid, gw) in enumerate(rows, start=1):
            try:
                mm = await bot.get_chat_member(m.chat.id, uid)
                name = mm.user.full_name
            except Exception:
                name = f"ID {uid}"
            text += f"  {i}. {name} — {gw}\n"
    else:
        text += "  пусто\n"
    cursor.execute("""
        SELECT user_id, bad_words FROM season_stats
        WHERE chat_id=? AND season_start=? AND bad_words > 0
        ORDER BY bad_words DESC LIMIT 5
    """, (m.chat.id, season))
    rows = cursor.fetchall()
    text += "\n❌ <b>Злые:</b>\n"
    if rows:
        for i, (uid, bw) in enumerate(rows, start=1):
            try:
                mm = await bot.get_chat_member(m.chat.id, uid)
                name = mm.user.full_name
            except Exception:
                name = f"ID {uid}"
            text += f"  {i}. {name} — {bw}\n"
    else:
        text += "  пусто\n"
    await m.reply(text)


@dp.message(Command("логи"))
async def cmd_logs(m: Message):
    if not is_admin(m.from_user.id):
        await m.reply("❌ Только админы.")
        return
    cursor.execute("""
        SELECT target_name, amount, reason, created_at FROM logs
        WHERE chat_id=? ORDER BY id DESC LIMIT 15
    """, (m.chat.id,))
    rows = cursor.fetchall()
    if not rows:
        await m.reply("Логов нет.")
        return
    text = "📜 <b>Последние 15:</b>\n\n"
    for name, am, reason, dt in rows:
        sign = "➕" if am > 0 else "➖"
        try:
            dt2 = datetime.fromisoformat(dt).strftime("%d.%m %H:%M")
        except Exception:
            dt2 = dt
        text += f"{sign} <b>{name}</b> — {reason} <i>({dt2})</i>\n"
    await m.reply(text)


@dp.message(Command("админ"))
async def cmd_add_admin(m: Message):
    if not is_admin(m.from_user.id):
        await m.reply("❌ Только админы.")
        return
    target = None
    if m.reply_to_message:
        target = m.reply_to_message.from_user
    else:
        p = (m.text or "").split(maxsplit=1)
        if len(p) >= 2 and p[1].startswith("@"):
            row = find_user_by_username(p[1], m.chat.id)
            if row:
                tid, tn = row
                target = type("U", (), {"id": tid, "full_name": tn, "username": tn})()
    if target is None:
        await m.reply("Использование: <code>/админ</code> ответом или <code>/админ @ник</code>")
        return
    if save_admin(target.id):
        await m.reply(f"✅ <b>{target.full_name}</b> теперь админ.")
    else:
        await m.reply(f"ℹ️ Уже админ.")


@dp.message(Command("разжаловать"))
async def cmd_remove_admin(m: Message):
    if not is_admin(m.from_user.id):
        await m.reply("❌ Только админы.")
        return
    target = None
    if m.reply_to_message:
        target = m.reply_to_message.from_user
    else:
        p = (m.text or "").split(maxsplit=1)
        if len(p) >= 2 and p[1].startswith("@"):
            row = find_user_by_username(p[1], m.chat.id)
            if row:
                tid, tn = row
                target = type("U", (), {"id": tid, "full_name": tn, "username": tn})()
    if target is None:
        await m.reply("Использование: <code>/разжаловать</code> ответом или <code>/разжаловать @ник</code>")
        return
    if target.id == m.from_user.id:
        await m.reply("Себя снять нельзя 🙂")
        return
    if remove_admin(target.id):
        await m.reply(f"✅ <b>{target.full_name}</b> больше не админ.")
    else:
        await m.reply(f"ℹ️ И так не админ.")


def parse_manual(message: Message):
    text = message.text or ""
    parts = text.split(maxsplit=3)
    amount = 1
    target = None
    reason = None
    if len(parts) >= 2 and parts[1].lstrip("-").isdigit():
        amount = max(1, abs(int(parts[1])))
        rest = parts[2:]
    else:
        rest = parts[1:]
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        reason = " ".join(rest) if rest else None
    elif rest and rest[0].startswith("@"):
        row = find_user_by_username(rest[0], message.chat.id)
        if row:
            tid, tn = row
            target = type("U", (), {"id": tid, "full_name": tn, "username": tn})()
            reason = " ".join(rest[1:]) if len(rest) > 1 else None
    else:
        target = message.from_user
        reason = " ".join(rest) if rest else None
    return amount, target, reason


@dp.message(Command("добро"))
async def cmd_dobro(m: Message):
    if not is_admin(m.from_user.id):
        await m.reply("❌ Только админы.")
        return
    amount, target, reason = parse_manual(m)
    if target is None:
        await m.reply("Не нашёл. Ответь на сообщение или укажи @ник.")
        return
    reason = reason or "хорошие слова"
    new = update_stars(target.id, m.chat.id, target.username or target.full_name, amount)
    add_log(m.chat.id, target.id, target.full_name, amount, f"ручная выдача: {reason}")
    await m.reply(f"✨ <b>{target.full_name}</b> +{amount} ⭐\nПричина: {reason}\nБаланс: <b>{new}</b> ⭐")


@dp.message(Command("зло"))
async def cmd_zlo(m: Message):
    if not is_admin(m.from_user.id):
        await m.reply("❌ Только админы.")
        return
    amount, target, reason = parse_manual(m)
    if target is None:
        await m.reply("Не нашёл.")
        return
    reason = reason or "плохие слова"
    new = update_stars(target.id, m.chat.id, target.username or target.full_name, -amount)
    add_log(m.chat.id, target.id, target.full_name, -amount, f"ручное снятие: {reason}")
    await m.reply(f"😔 <b>{target.full_name}</b> −{amount} ⭐\nПричина: {reason}\nБаланс: <b>{new}</b> ⭐")
    # ============================================================
# КАЗИНО — РУЛЕТКА
# ============================================================
RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}


@dp.message(Command("рулетка"))
async def cmd_roulette(m: Message):
    p = (m.text or "").split(maxsplit=2)
    if len(p) < 3:
        await m.reply(
            "Использование: <code>/рулетка 100 красное</code>\n"
            "красное/чёрное ×2, чет/нечет ×2, зеро ×14, число ×36.\n"
            f"Ставка {CASINO_MIN_BET}–{CASINO_MAX_BET}"
        )
        return
    try:
        bet = int(p[1])
    except ValueError:
        await m.reply("Ставка должна быть числом.")
        return
    if bet < CASINO_MIN_BET or bet > CASINO_MAX_BET:
        await m.reply(f"Ставка от {CASINO_MIN_BET} до {CASINO_MAX_BET}.")
        return
    choice = p[2].strip().lower()
    uid, cid, name = m.from_user.id, m.chat.id, m.from_user.username or m.from_user.full_name
    if get_stars(uid, cid) < bet:
        await m.reply("Недостаточно звёзд.")
        return
    roll = random.randint(0, 36)
    color = "красное" if roll in RED_NUMBERS else ("чёрное" if roll != 0 else "зеро")
    parity = "чет" if roll != 0 and roll % 2 == 0 else ("нечет" if roll != 0 else "зеро")
    win = False
    mult = 0
    if choice == "красное" and color == "красное":
        win, mult = True, 2
    elif choice == "чёрное" and color == "чёрное":
        win, mult = True, 2
    elif choice == "чет" and parity == "чет":
        win, mult = True, 2
    elif choice == "нечет" and parity == "нечет":
        win, mult = True, 2
    elif choice == "зеро" and roll == 0:
        win, mult = True, 14
    elif choice.isdigit() and int(choice) == roll:
        win, mult = True, 36
    if win:
        profit = bet * (mult - 1)
        new = update_stars(uid, cid, name, profit)
        update_casino_stats(uid, cid, won=profit)
        update_season_stat(uid, cid, name, won=profit)
        add_log(cid, uid, name, profit, f"казино: +{profit}")
        await m.reply(f"🎰 Выпало {roll} ({color}, {parity})\n🎉 +{profit} ⭐\nБаланс: <b>{new}</b>")
    else:
        new = update_stars(uid, cid, name, -bet)
        update_casino_stats(uid, cid, lost=bet)
        update_season_stat(uid, cid, name, lost=bet)
        add_log(cid, uid, name, -bet, f"казино: −{bet}")
        await m.reply(f"🎰 Выпало {roll} ({color}, {parity})\n😔 −{bet} ⭐\nБаланс: <b>{new}</b>")


# ============================================================
# КОСТИ
# ============================================================
@dp.message(Command("кости"))
async def cmd_dice(m: Message):
    p = (m.text or "").split(maxsplit=2)
    if len(p) < 2:
        await m.reply("Использование: <code>/кости @ник 100</code> или ответом <code>/кости 100</code>")
        return
    target = None
    bet = None
    if m.reply_to_message:
        target = m.reply_to_message.from_user
        try:
            bet = int(p[1])
        except ValueError:
            await m.reply("Ставка должна быть числом.")
            return
    else:
        if p[1].startswith("@"):
            row = find_user_by_username(p[1], m.chat.id)
            if not row:
                await m.reply(f"Не нашёл {p[1]}. Пусть напишет что-нибудь в чат, или ответь на его сообщение.")
                return
            tid, tn = row
            target = type("U", (), {"id": tid, "full_name": tn, "username": tn})()
            try:
                bet = int(p[2])
            except (ValueError, IndexError):
                await m.reply("Ставка должна быть числом.")
                return
        else:
            await m.reply("Укажи @ник или ответь на сообщение.")
            return
    if target.id == m.from_user.id:
        await m.reply("Себе нельзя 🙂")
        return
    if bet < DICE_MIN_BET or bet > DICE_MAX_BET:
        await m.reply(f"Ставка от {DICE_MIN_BET} до {DICE_MAX_BET}.")
        return
    if get_stars(m.from_user.id, m.chat.id) < bet:
        await m.reply("У тебя недостаточно звёзд.")
        return
    if get_stars(target.id, m.chat.id) < bet:
        await m.reply(f"У <b>{target.full_name}</b> недостаточно звёзд.")
        return
    pending_duels.setdefault(m.chat.id, {})[target.id] = {
        "challenger_id": m.from_user.id,
        "challenger_name": m.from_user.full_name,
        "bet": bet,
    }
    await m.reply(
        f"🎲 <b>{m.from_user.full_name}</b> вызывает <b>{target.full_name}</b>\n"
        f"Ставка: <b>{bet}</b> ⭐\n\n"
        f"<b>{target.full_name}</b>, напиши <code>/принять</code> или <code>/отклонить</code>."
    )


@dp.message(Command("принять"))
async def cmd_accept(m: Message):
    cid = m.chat.id
    uid = m.from_user.id
    if cid not in pending_duels or uid not in pending_duels[cid]:
        await m.reply("Тебе никто не бросал вызов.")
        return
    duel = pending_duels[cid].pop(uid)
    ch_id = duel["challenger_id"]
    ch_name = duel["challenger_name"]
    bet = duel["bet"]
    ac_name = m.from_user.full_name
    if get_stars(ch_id, cid) < bet or get_stars(uid, cid) < bet:
        await m.reply("У кого-то не хватает звёзд. Отменено.")
        return
    r_ch = random.randint(1, 6)
    r_ac = random.randint(1, 6)
    if r_ch > r_ac:
        new_ch = update_stars(ch_id, cid, ch_name, bet)
        new_ac = update_stars(uid, cid, ac_name, -bet)
        update_casino_stats(ch_id, cid, won=bet)
        update_casino_stats(uid, cid, lost=bet)
        update_season_stat(ch_id, cid, ch_name, won=bet)
        update_season_stat(uid, cid, ac_name, lost=bet)
        add_log(cid, ch_id, ch_name, bet, f"кости vs {ac_name}")
        add_log(cid, uid, ac_name, -bet, f"кости vs {ch_name}")
        await m.reply(
            f"🎲 {ch_name}: {r_ch}\n🎲 {ac_name}: {r_ac}\n\n"
            f"🏆 Победил <b>{ch_name}</b>! +{bet} ⭐\n"
            f"Балансы: {ch_name} {new_ch} | {ac_name} {new_ac}"
        )
    elif r_ac > r_ch:
        new_ac = update_stars(uid, cid, ac_name, bet)
        new_ch = update_stars(ch_id, cid, ch_name, -bet)
        update_casino_stats(uid, cid, won=bet)
        update_casino_stats(ch_id, cid, lost=bet)
        update_season_stat(uid, cid, ac_name, won=bet)
        update_season_stat(ch_id, cid, ch_name, lost=bet)
        add_log(cid, uid, ac_name, bet, f"кости vs {ch_name}")
        add_log(cid, ch_id, ch_name, -bet, f"кости vs {ac_name}")
        await m.reply(
            f"🎲 {ch_name}: {r_ch}\n🎲 {ac_name}: {r_ac}\n\n"
            f"🏆 Победил <b>{ac_name}</b>! +{bet} ⭐\n"
            f"Балансы: {ch_name} {new_ch} | {ac_name} {new_ac}"
        )
    else:
        await m.reply(f"🎲 {ch_name}: {r_ch}\n🎲 {ac_name}: {r_ac}\n\n🤝 Ничья!")


@dp.message(Command("отклонить"))
async def cmd_decline(m: Message):
    cid = m.chat.id
    uid = m.from_user.id
    if cid in pending_duels and uid in pending_duels[cid]:
        pending_duels[cid].pop(uid)
        await m.reply("❌ Отклонено.")
    else:
        await m.reply("Тебе никто не бросал вызов.")


# ============================================================
# КРАЖА
# ============================================================
@dp.message(Command("украсть"))
async def cmd_steal(m: Message):
    target = None
    if m.reply_to_message:
        target = m.reply_to_message.from_user
    else:
        p = (m.text or "").split(maxsplit=1)
        if len(p) >= 2 and p[1].startswith("@"):
            row = find_user_by_username(p[1], m.chat.id)
            if row:
                tid, tn = row
                target = type("U", (), {"id": tid, "full_name": tn, "username": tn})()
    if target is None:
        await m.reply("Использование: <code>/украсть</code> ответом или <code>/украсть @ник</code>")
        return
    if target.id == m.from_user.id:
        await m.reply("У себя красть нельзя 🙂")
        return
    if target.is_bot:
        await m.reply("У ботов красть нельзя 🙂")
        return
    thief_id = m.from_user.id
    thief_name = m.from_user.username or m.from_user.full_name
    cid = m.chat.id
    cursor.execute("SELECT last_steal FROM steal_cooldowns WHERE thief_id=? AND target_id=? AND chat_id=?",
                   (thief_id, target.id, cid))
    r = cursor.fetchone()
    if r:
        last = datetime.fromisoformat(r[0])
        if datetime.now() - last < timedelta(hours=STEAL_COOLDOWN_HOURS):
            left = timedelta(hours=STEAL_COOLDOWN_HOURS) - (datetime.now() - last)
            await m.reply(f"⏱️ Осталось {left.seconds//3600}ч {(left.seconds%3600)//60}м.")
            return
    tbal = get_stars(target.id, cid)
    if tbal < STEAL_MIN_BALANCE:
        await m.reply(f"У <b>{target.full_name}</b> меньше {STEAL_MIN_BALANCE} ⭐.")
        return
    cursor.execute("""
        INSERT INTO steal_cooldowns (thief_id, target_id, chat_id, last_steal)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(thief_id, target_id, chat_id) DO UPDATE SET last_steal=?
    """, (thief_id, target.id, cid, datetime.now().isoformat(), datetime.now().isoformat()))
    db.commit()
    if random.random() < STEAL_SUCCESS_CHANCE:
        amt = random.randint(STEAL_MIN_AMOUNT, STEAL_MAX_AMOUNT)
        amt = min(amt, tbal)
        update_stars(thief_id, cid, thief_name, amt)
        new_t = update_stars(target.id, cid, target.full_name, -amt)
        add_log(cid, thief_id, thief_name, amt, f"украл у {target.full_name}")
        add_log(cid, target.id, target.full_name, -amt, f"обокрал {thief_name}")
        await m.reply(f"🥷 Успех! Украл <b>{amt}</b> ⭐ у {target.full_name}.\nУ него осталось {new_t} ⭐")
    else:
        update_stars(thief_id, cid, thief_name, -STEAL_FAIL_PENALTY)
        await m.reply(f"🚨 Провал! −{STEAL_FAIL_PENALTY} ⭐")


# ============================================================
# СВОДКА
# ============================================================
@dp.message(Command("сводка"))
async def cmd_weekly(m: Message):
    await send_weekly_report(m.chat.id)


async def send_weekly_report(chat_id: int):
    prev_start = get_season_start() - timedelta(days=7)
    prev_end = get_season_start()
    season = prev_start.isoformat()
    text = f"📊 <b>Сводка {prev_start.strftime('%d.%m')} — {prev_end.strftime('%d.%m')}</b>\n\n"
    cursor.execute("""
        SELECT user_id, good_words FROM season_stats
        WHERE chat_id=? AND season_start=? AND good_words > 0
        ORDER BY good_words DESC LIMIT 3
    """, (chat_id, season))
    rows = cursor.fetchall()
    text += "✅ Добрые:\n"
    for i, (uid, gw) in enumerate(rows, start=1):
        try:
            mm = await bot.get_chat_member(chat_id, uid)
            name = mm.user.full_name
        except Exception:
            name = f"ID {uid}"
        text += f"  {i}. {name} — {gw}\n"
    cursor.execute("""
        SELECT user_id, bad_words FROM season_stats
        WHERE chat_id=? AND season_start=? AND bad_words > 0
        ORDER BY bad_words DESC LIMIT 3
    """, (chat_id, season))
    rows = cursor.fetchall()
    text += "\n❌ Злые:\n"
    for i, (uid, bw) in enumerate(rows, start=1):
        try:
            mm = await bot.get_chat_member(chat_id, uid)
            name = mm.user.full_name
        except Exception:
            name = f"ID {uid}"
        text += f"  {i}. {name} — {bw}\n"
    try:
        await bot.send_message(chat_id, text)
    except Exception as e:
        print(f"[WEEKLY] ошибка: {e}")


# ============================================================
# АВТО-СЛОВА — ГЛАВНЫЙ ОБРАБОТЧИК
# ВАЖНО: он должен быть В САМОМ КОНЦЕ, после всех команд!
# ============================================================
@dp.message(F.text)
async def handle_message(message: Message):
    try:
        user = message.from_user
        if not user or user.is_bot:
            return

        text = message.text or ""
        chat_id = message.chat.id
        chat_type = message.chat.type

        # Диагностика — увидим в логах
        print(f"[MSG] {user.full_name} | {chat_type} | {text!r}")

        # Запоминаем только в группах
        if chat_type in ("group", "supergroup"):
            ensure_user(user.id, chat_id, user.username or user.full_name)

        # Команды пропускаем
        if text.startswith("/"):
            return

        # Не в группе — выходим
        if chat_type not in ("group", "supergroup"):
            print(f"[SKIP] не группа: {chat_type}")
            return

        if not AUTO_STARS_ENABLED:
            print("[SKIP] авто выключены")
            return

        bad_w, bad_v = find_best_word(text, BAD_WORDS)
        good_w, good_v = find_best_word(text, GOOD_WORDS)
        print(f"[FIND] good={good_w}(+{good_v}) bad={bad_w}(-{bad_v})")

        if bad_w:
            if same_word_used_recently(user.id, chat_id, bad_w, SAME_BAD_WORD_COOLDOWN_MINUTES):
                print(f"[SKIP] плохое {bad_w} недавно")
                return
            delta = -bad_v
            reason = f"авто: плохое «{bad_w}» (−{bad_v})"
            inc_word_stat(user.id, chat_id, user.username or user.full_name, is_good=False)
            update_season_stat(user.id, chat_id, user.username or user.full_name, bad=1)
        elif good_w:
            if plus_count_last_hour(user.id, chat_id) >= MAX_PLUS_PER_HOUR:
                print("[SKIP] плюсовой лимит в час")
                return
            if plus_sum_last_day(user.id, chat_id) >= MAX_PLUS_PER_DAY:
                print("[SKIP] плюсовой лимит в сутки")
                return
            if same_word_used_recently(user.id, chat_id, good_w, SAME_WORD_COOLDOWN_HOURS * 60):
                print(f"[SKIP] хорошее {good_w} недавно")
                return
            delta = good_v
            reason = f"авто: хорошее «{good_w}» (+{good_v})"
            inc_word_stat(user.id, chat_id, user.username or user.full_name, is_good=True)
            update_season_stat(user.id, chat_id, user.username or user.full_name, good=1)
        else:
            print("[SKIP] слов не найдено")
            return

        new = update_stars(user.id, chat_id, user.username or user.full_name, delta)
        add_log(chat_id, user.id, user.full_name, delta, reason)
        print(f"[OK] {user.full_name}: {delta}, баланс {new}")

        if DEBUG_AUTO:
            sign = "➕" if delta > 0 else "➖"
            await message.reply(f"{sign} <b>{user.full_name}</b>: {reason}\nБаланс: <b>{new}</b> ⭐")

    except Exception as e:
        print(f"[ERROR] в handle_message: {e}")
        import traceback
        traceback.print_exc()


# ============================================================
# ЗАПУСК
# ============================================================
async def main():
    print("=" * 50)
    print("Бот Добро-Звёзды запущен!")
    print(f"Авто-звёзды: {'ВКЛ' if AUTO_STARS_ENABLED else 'ВЫКЛ'}")
    print(f"Админов: {len(load_admins())}")
    print("=" * 50)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
