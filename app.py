import asyncio
import os
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

# ============================================================
# АНТИФАРМ
# ============================================================
MAX_PLUS_PER_HOUR = 3
MAX_PLUS_PER_DAY = 20
SAME_WORD_COOLDOWN_HOURS = 6
SAME_BAD_WORD_COOLDOWN_MINUTES = 1

AUTO_STARS_ENABLED = True
DEBUG_AUTO = True


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
    new_lines = [l for l in lines if l.strip() != str(uid)]
    if len(new_lines) == len(lines):
        return False
    with open("admins.txt", "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    return True


def is_admin(uid):
    return uid in load_admins()


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
db.commit()


def get_stars(uid, cid):
    cursor.execute("SELECT stars FROM users WHERE user_id=? AND chat_id=?", (uid, cid))
    r = cursor.fetchone()
    return r[0] if r else 0


def update_stars(uid, cid, un, amount):
    new = get_stars(uid, cid) + amount
    cursor.execute("""
        INSERT INTO users (user_id, chat_id, username, stars) VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, chat_id) DO UPDATE SET stars=?, username=?
    """, (uid, cid, un, new, new, un))
    db.commit()
    return new


def add_log(cid, tid, tn, amount, reason):
    cursor.execute("""
        INSERT INTO logs (chat_id, target_id, target_name, amount, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (cid, tid, tn, amount, reason, datetime.now().isoformat()))
    db.commit()


def find_best_word(text, words):
    t = text.lower()
    best_w, best_v = None, 0
    for w, v in words.items():
        if w in t and v > best_v:
            best_w, best_v = w, v
    return best_w, best_v


def plus_count_last_hour(uid, cid):
    cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
    cursor.execute("""
        SELECT COUNT(*) FROM logs
        WHERE target_id=? AND chat_id=? AND amount > 0
        AND reason LIKE 'авто:%' AND created_at > ?
    """, (uid, cid, cutoff))
    return cursor.fetchone()[0]


def plus_sum_last_day(uid, cid):
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0) FROM logs
        WHERE target_id=? AND chat_id=? AND amount > 0
        AND reason LIKE 'авто:%' AND created_at > ?
    """, (uid, cid, cutoff))
    return cursor.fetchone()[0]


def same_word_used_recently(uid, cid, word, minutes):
    cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
    cursor.execute("""
        SELECT COUNT(*) FROM logs
        WHERE target_id=? AND chat_id=? AND reason LIKE ?
        AND created_at > ?
    """, (uid, cid, f"%«{word}»%", cutoff))
    return cursor.fetchone()[0] > 0


# ============================================================
# КОМАНДЫ
# ============================================================

@dp.message(Command("start", "help", "помощь"))
async def cmd_help(m: Message):
    await m.answer(
        "👋 <b>Бот Добро-Звёзды</b>\n\n"
        "📌 /профиль — свои звёзды\n"
        "📌 /профиль (ответом) — чужие\n"
        "📌 /таблица — топ-10\n"
        "📌 /антитоп — самые злые\n"
        "📌 /тест_авто фраза — что бот видит\n\n"
        "<b>Админам:</b>\n"
        "📌 /добро N причина — выдать себе N звёзд\n"
        "📌 /добро N @ник причина — выдать другому\n"
        "📌 /добро N причина (ответом) — выдать тому, кому ответил\n"
        "📌 /зло N причина — снять у себя\n"
        "📌 /зло N @ник причина — снять у другого\n"
        "📌 /авто вкл|выкл\n"
        "📌 /админ @ник — назначить админа\n"
        "📌 /разжаловать @ник — снять админа\n"
        "📌 /логи — последние операции\n\n"
        "⭐ Веса: +1/+2/+5/+10 и −1/−2/−5/−10."
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
    if not is_admin(m.from_user.id):
        await m.reply("❌ Только админы.")
        return
    p = (m.text or "").split(maxsplit=1)
    if len(p) < 2 or p[1] not in ("вкл", "выкл"):
        await m.reply(f"Авто: <b>{'вкл' if AUTO_STARS_ENABLED else 'выкл'}</b>\n/авто вкл или /авто выкл")
        return
    AUTO_STARS_ENABLED = (p[1] == "вкл")
    await m.reply(f"✅ Авто теперь <b>{'включены' if AUTO_STARS_ENABLED else 'выключены'}</b>.")


@dp.message(Command("профиль"))
async def cmd_profile(m: Message):
    t = m.reply_to_message.from_user if m.reply_to_message else m.from_user
    s = get_stars(t.id, m.chat.id)
    if s < 0:
        e = "💀"
    elif s == 0:
        e = "😐"
    elif s < 5:
        e = "🙂"
    elif s < 15:
        e = "😊"
    elif s < 50:
        e = "🌟"
    else:
        e = "👑"
    await m.reply(f"{e} <b>{t.full_name}</b>\n🆔 <code>{t.id}</code>\n⭐ <b>{s}</b>")


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
            un = p[1].lstrip("@")
            cursor.execute(
                "SELECT user_id, username FROM users WHERE username=? AND chat_id=?",
                (un, m.chat.id)
            )
            row = cursor.fetchone()
            if row:
                tid, tn = row
                target = type("U", (), {"id": tid, "full_name": tn, "username": tn})()
    if target is None:
        await m.reply("Использование: <code>/админ</code> ответом или <code>/админ @ник</code>")
        return
    if save_admin(target.id):
        await m.reply(f"✅ <b>{target.full_name}</b> теперь админ.")
    else:
        await m.reply(f"ℹ️ <b>{target.full_name}</b> уже админ.")


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
            un = p[1].lstrip("@")
            cursor.execute(
                "SELECT user_id, username FROM users WHERE username=? AND chat_id=?",
                (un, m.chat.id)
            )
            row = cursor.fetchone()
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
        await m.reply(f"ℹ️ <b>{target.full_name}</b> и так не админ.")


# --- Ручные выдачи: СЕБЕ МОЖНО ---

def parse_manual(message: Message):
    """
    Возвращает (amount, target, reason).
    target = None означает, что выдаём САМОМУ СЕБЕ.
    """
    text = message.text or ""
    parts = text.split(maxsplit=3)
    amount = 1
    target = None
    reason = None

    if len(parts) >= 2 and parts[1].isdigit():
        amount = max(1, int(parts[1]))
        rest = parts[2:]
    else:
        rest = parts[1:]

    if message.reply_to_message:
        # Ответом — выдаём тому, кому ответили
        target = message.reply_to_message.from_user
        reason = " ".join(rest) if rest else None
    elif rest and rest[0].startswith("@"):
        # По @нику
        un = rest[0].lstrip("@")
        cursor.execute(
            "SELECT user_id, username FROM users WHERE username=? AND chat_id=?",
            (un, message.chat.id)
        )
        row = cursor.fetchone()
        if row:
            tid, tn = row
            target = type("U", (), {"id": tid, "full_name": tn, "username": tn})()
            reason = " ".join(rest[1:]) if len(rest) > 1 else None
        else:
            # ник указан, но не найден
            return amount, "NOT_FOUND", None
    else:
        # Ни ответа, ни @ника — выдаём СЕБЕ
        target = message.from_user
        reason = " ".join(rest) if rest else None

    return amount, target, reason


@dp.message(Command("добро"))
async def cmd_dobro(m: Message):
    if not is_admin(m.from_user.id):
        await m.reply("❌ Только админы.")
        return

    amount, target, reason = parse_manual(m)

    if target == "NOT_FOUND":
        await m.reply("Не нашёл такого пользователя в базе этого чата. Пусть он сначала напишет что-нибудь.")
        return

    if target is None:
        await m.reply("Ошибка: не удалось определить цель.")
        return

    reason = reason or "хорошие слова"
    new = update_stars(target.id, m.chat.id, target.username or target.full_name, amount)
    add_log(m.chat.id, target.id, target.full_name, amount, f"ручная выдача: {reason}")

    await m.reply(
        f"✨ <b>{target.full_name}</b> +{amount} ⭐\n"
        f"Причина: {reason}\n"
        f"Баланс: <b>{new}</b> ⭐"
    )


@dp.message(Command("зло"))
async def cmd_zlo(m: Message):
    if not is_admin(m.from_user.id):
        await m.reply("❌ Только админы.")
        return

    amount, target, reason = parse_manual(m)

    if target == "NOT_FOUND":
        await m.reply("Не нашёл такого пользователя в базе этого чата.")
        return

    if target is None:
        await m.reply("Ошибка: не удалось определить цель.")
        return

    reason = reason or "плохие слова"
    new = update_stars(target.id, m.chat.id, target.username or target.full_name, -amount)
    add_log(m.chat.id, target.id, target.full_name, -amount, f"ручное снятие: {reason}")

    await m.reply(
        f"😔 <b>{target.full_name}</b> −{amount} ⭐\n"
        f"Причина: {reason}\n"
        f"Баланс: <b>{new}</b> ⭐"
    )


# ============================================================
# АВТО-ЗВЁЗДЫ
# ============================================================

@dp.message(F.text)
async def handle_message(message: Message):
    if not message.from_user or message.from_user.is_bot:
        return

    user = message.from_user
    text = message.text or ""
    chat_id = message.chat.id
    chat_type = message.chat.type

    print(f"[MSG] {user.full_name} | {chat_type} | {text!r}")

    if chat_type in ("group", "supergroup"):
        cursor.execute("""
            INSERT INTO users (user_id, chat_id, username, stars) VALUES (?, ?, ?, 0)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET username=?
        """, (
            user.id, chat_id,
            user.username or user.full_name,
            user.username or user.full_name,
        ))
        db.commit()

    if text.startswith("/"):
        return

    if chat_type not in ("group", "supergroup"):
        return

    if not AUTO_STARS_ENABLED:
        return

    bad_w, bad_v = find_best_word(text, BAD_WORDS)
    good_w, good_v = find_best_word(text, GOOD_WORDS)

    if bad_w:
        if same_word_used_recently(user.id, chat_id, bad_w, SAME_BAD_WORD_COOLDOWN_MINUTES):
            return
        delta = -bad_v
        reason = f"авто: плохое «{bad_w}» (−{bad_v})"
    elif good_w:
        if plus_count_last_hour(user.id, chat_id) >= MAX_PLUS_PER_HOUR:
            return
        if plus_sum_last_day(user.id, chat_id) >= MAX_PLUS_PER_DAY:
            return
        if same_word_used_recently(user.id, chat_id, good_w, SAME_WORD_COOLDOWN_HOURS * 60):
            return
        delta = good_v
        reason = f"авто: хорошее «{good_w}» (+{good_v})"
    else:
        return

    new = update_stars(user.id, chat_id, user.username or user.full_name, delta)
    add_log(chat_id, user.id, user.full_name, delta, reason)

    if DEBUG_AUTO:
        sign = "➕" if delta > 0 else "➖"
        await message.reply(
            f"{sign} <b>{user.full_name}</b>: {reason}\n"
            f"Баланс: <b>{new}</b> ⭐"
        )


@dp.message(F.new_chat_members)
async def welcome(message: Message):
    for m in message.new_chat_members:
        if m.is_bot:
            continue
        await message.answer(
            f"👋 <b>{m.full_name}</b>, добро пожаловать!\n\n"
            f"Свои звёзды: /профиль\nТоп: /таблица"
        )


async def main():
    print("=" * 40)
    print("Бот Добро-Звёзды запущен!")
    print(f"Авто-звёзды: {'ВКЛ' if AUTO_STARS_ENABLED else 'ВЫКЛ'}")
    print(f"Админов: {len(load_admins())}")
    print("=" * 40)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
