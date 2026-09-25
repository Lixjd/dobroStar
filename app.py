# ============================================================
# КОМАНДЫ
# ============================================================

@dp.message(Command("start", "help", "помощь"))
async def cmd_help(m: Message):
    await m.answer(
        "👋 <b>Бот Добро-Звёзды</b>\n\n"
        "📌 <b>Общее:</b>\n"
        "/профиль — свой профиль\n"
        "/профиль (ответом) — чужой\n"
        "/таблица — топ по звёздам\n"
        "/антитоп — самый злой\n"
        "/топ_сезона — топы за эту неделю\n"
        "/сезон — инфо о сезоне\n"
        "/сводка — отчёт за неделю\n"
        "/тест_авто фраза\n\n"
        "🎲 <b>Игры:</b>\n"
        "/рулетка 100 красное — ставка на цвет\n"
        "  (красное ×2, чёрное ×2, чёт ×2, нечет ×2, зеро ×14, число ×36)\n"
        "/кости @ник 100 — вызов на дуэль (1 кубик)\n"
        "/принять — принять вызов\n"
        "/отклонить — отклонить\n"
        "/украсть @ник — попытка кражи\n\n"
        "🛠 <b>Админам:</b>\n"
        "/добро N @ник причина\n"
        "/зло N @ник причина\n"
        "/авто вкл|выкл\n"
        "/админ @ник\n"
        "/разжаловать @ник\n"
        "/логи"
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
        await m.reply(f"Авто: <b>{'вкл' if AUTO_STARS_ENABLED else 'выкл'}</b>")
        return
    AUTO_STARS_ENABLED = (p[1] == "вкл")
    await m.reply(f"✅ Авто <b>{'включены' if AUTO_STARS_ENABLED else 'выключены'}</b>.")


@dp.message(Command("сезон"))
async def cmd_season(m: Message):
    start = get_season_start()
    end = get_season_end()
    now = datetime.now()
    left = end - now
    days = left.days
    hours = left.seconds // 3600
    await m.reply(
        f"📅 <b>Текущий сезон</b>\n\n"
        f"Начало: <b>{start.strftime('%d.%m.%Y %H:%M')}</b>\n"
        f"Конец: <b>{end.strftime('%d.%m.%Y %H:%M')}</b>\n"
        f"Осталось: <b>{days}д {hours}ч</b>\n\n"
        f"Новый сезон стартует каждую пятницу в 00:00."
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
        f"{e} <b>Профиль {t.full_name}</b>\n"
        f"🆔 <code>{t.id}</code>\n\n"
        f"⭐ <b>Баланс:</b> {s}\n\n"
        f"📝 <b>Слова (всего):</b>\n"
        f"  ✅ Хороших: {gw}\n"
        f"  ❌ Плохих: {bw}\n\n"
        f"🎰 <b>Казино (всё время):</b>\n"
        f"  Выиграно: {cw}\n"
        f"  Проиграно: {cl}\n\n"
        f"📅 <b>За этот сезон:</b>\n"
        f"  🎰 Выиграно: {sw}\n"
        f"  🎰 Проиграно: {sl}\n"
        f"  ✅ Хороших слов: {sg}\n"
        f"  ❌ Плохих слов: {sb}"
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
    text = "📅 <b>Топы за текущий сезон</b>\n\n"

    # Топ по доброте (good_words)
    cursor.execute("""
        SELECT user_id, good_words FROM season_stats
        WHERE chat_id=? AND season_start=? AND good_words > 0
        ORDER BY good_words DESC LIMIT 5
    """, (m.chat.id, season))
    rows = cursor.fetchall()
    text += "✅ <b>Самые добрые:</b>\n"
    if rows:
        for i, (uid, gw) in enumerate(rows, start=1):
            try:
                mm = await bot.get_chat_member(m.chat.id, uid)
                name = mm.user.full_name
            except Exception:
                name = f"ID {uid}"
            text += f"  {i}. {name} — {gw} хороших слов\n"
    else:
        text += "  пусто\n"

    # Топ по злу
    cursor.execute("""
        SELECT user_id, bad_words FROM season_stats
        WHERE chat_id=? AND season_start=? AND bad_words > 0
        ORDER BY bad_words DESC LIMIT 5
    """, (m.chat.id, season))
    rows = cursor.fetchall()
    text += "\n❌ <b>Самые злые:</b>\n"
    if rows:
        for i, (uid, bw) in enumerate(rows, start=1):
            try:
                mm = await bot.get_chat_member(m.chat.id, uid)
                name = mm.user.full_name
            except Exception:
                name = f"ID {uid}"
            text += f"  {i}. {name} — {bw} плохих слов\n"
    else:
        text += "  пусто\n"

    # Топ казино за сезон
    cursor.execute("""
        SELECT user_id, won, lost FROM season_stats
        WHERE chat_id=? AND season_start=? AND (won > 0 OR lost > 0)
        ORDER BY (won - lost) DESC LIMIT 5
    """, (m.chat.id, season))
    rows = cursor.fetchall()
    text += "\n🎰 <b>Казино (баланс выигрыш-проигрыш):</b>\n"
    if rows:
        for i, (uid, w, l) in enumerate(rows, start=1):
            try:
                mm = await bot.get_chat_member(m.chat.id, uid)
                name = mm.user.full_name
            except Exception:
                name = f"ID {uid}"
            diff = w - l
            sign = "+" if diff >= 0 else ""
            text += f"  {i}. {name} — {sign}{diff}\n"
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


# --- Управление админами ---

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
            cursor.execute("SELECT user_id, username FROM users WHERE username=? AND chat_id=?", (un, m.chat.id))
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
            un = p[1].lstrip("@")
            cursor.execute("SELECT user_id, username FROM users WHERE username=? AND chat_id=?", (un, m.chat.id))
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
        await m.reply(f"ℹ️ И так не админ.")


# --- Ручные выдачи ---

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
        un = rest[0].lstrip("@")
        cursor.execute("SELECT user_id, username FROM users WHERE username=? AND chat_id=?", (un, message.chat.id))
        row = cursor.fetchone()
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
        await m.reply("Не нашёл пользователя. Ответь на сообщение или укажи @ник.")
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
        await m.reply("Не нашёл пользователя.")
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
            "Использование: <code>/рулетка 100 красное</code>\n\n"
            "Ставки:\n"
            "• <b>красное</b> ×2\n"
            "• <b>чёрное</b> ×2\n"
            "• <b>чет</b> ×2\n"
            "• <b>нечет</b> ×2\n"
            "• <b>зеро</b> ×14\n"
            "• число <b>0-36</b> ×36\n\n"
            f"Ставка: от {CASINO_MIN_BET} до {CASINO_MAX_BET}"
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

    # Проверка баланса
    current = get_stars(uid, cid)
    if current < bet:
        await m.reply(f"У тебя только {current} ⭐, а ставка {bet}.")
        return

    roll = random.randint(0, 36)
    color = "красное" if roll in RED_NUMBERS else ("чёрное" if roll != 0 else "зеро")
    parity = "чет" if roll != 0 and roll % 2 == 0 else ("нечет" if roll != 0 else "зеро")

    win = False
    multiplier = 0

    if choice == "красное" and color == "красное":
        win, multiplier = True, 2
    elif choice == "чёрное" and color == "чёрное":
        win, multiplier = True, 2
    elif choice == "чет" and parity == "чет":
        win, multiplier = True, 2
    elif choice == "нечет" and parity == "нечет":
        win, multiplier = True, 2
    elif choice == "зеро" and roll == 0:
        win, multiplier = True, 14
    elif choice.isdigit() and int(choice) == roll:
        win, multiplier = True, 36

    if win:
        profit = bet * (multiplier - 1)
        new = update_stars(uid, cid, name, profit)
        update_casino_stats(uid, cid, won=profit)
        update_season_stat(uid, cid, name, won=profit)
        add_log(cid, uid, name, profit, f"казино: выигрыш {profit}")
        await m.reply(
            f"🎰 Выпало: <b>{roll}</b> ({color}, {parity})\n\n"
            f"🎉 <b>Победа!</b> +{profit} ⭐\n"
            f"Баланс: <b>{new}</b> ⭐"
        )
    else:
        new = update_stars(uid, cid, name, -bet)
        update_casino_stats(uid, cid, lost=bet)
        update_season_stat(uid, cid, name, lost=bet)
        add_log(cid, uid, name, -bet, f"казино: проигрыш {bet}")
        await m.reply(
            f"🎰 Выпало: <b>{roll}</b> ({color}, {parity})\n\n"
            f"😔 <b>Проигрыш.</b> −{bet} ⭐\n"
            f"Баланс: <b>{new}</b> ⭐"
        )


# ============================================================
# КОСТИ (ДУЭЛИ)
# ============================================================

@dp.message(Command("кости"))
async def cmd_dice(m: Message):
    p = (m.text or "").split(maxsplit=2)
    if len(p) < 3:
        await m.reply("Использование: <code>/кости @ник 100</code> — ответом или с ником.")
        return

    # Пытаемся понять, где @ник, а где ставка
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
            un = p[1].lstrip("@")
            cursor.execute("SELECT user_id, username FROM users WHERE username=? AND chat_id=?", (un, m.chat.id))
            row = cursor.fetchone()
            if not row:
                await m.reply("Не нашёл такого. Пусть напишет что-нибудь в чат.")
                return
            tid, tn = row
            target = type("U", (), {"id": tid, "full_name": tn, "username": tn})()
            try:
                bet = int(p[2])
            except ValueError:
                await m.reply("Ставка должна быть числом.")
                return
        else:
            await m.reply("Укажи @ник или ответь на сообщение.")
            return

    if target.id == m.from_user.id:
        await m.reply("Себе вызов бросить нельзя 🙂")
        return

    if bet < DICE_MIN_BET or bet > DICE_MAX_BET:
        await m.reply(f"Ставка от {DICE_MIN_BET} до {DICE_MAX_BET}.")
        return

    # Проверка балансов обоих
    my_balance = get_stars(m.from_user.id, m.chat.id)
    his_balance = get_stars(target.id, m.chat.id)

    if my_balance < bet:
        await m.reply(f"У тебя только {my_balance} ⭐, а ставка {bet}.")
        return
    if his_balance < bet:
        await m.reply(f"У <b>{target.full_name}</b> только {his_balance} ⭐, а ставка {bet}.")
        return

    # Сохраняем вызов
    pending_duels.setdefault(m.chat.id, {})[target.id] = {
        "challenger_id": m.from_user.id,
        "challenger_name": m.from_user.full_name,
        "bet": bet,
    }

    await m.reply(
        f"🎲 <b>{m.from_user.full_name}</b> вызывает <b>{target.full_name}</b> на дуэль!\n"
        f"Ставка: <b>{bet}</b> ⭐\n\n"
        f"<b>{target.full_name}</b>, чтобы принять — напиши <code>/принять</code>\n"
        f"Чтобы отклонить — <code>/отклонить</code>"
    )


@dp.message(Command("принять"))
async def cmd_accept(m: Message):
    cid = m.chat.id
    uid = m.from_user.id

    if cid not in pending_duels or uid not in pending_duels[cid]:
        await m.reply("Тебе никто не бросал вызов.")
        return

    duel = pending_duels[cid].pop(uid)
    challenger_id = duel["challenger_id"]
    challenger_name = duel["challenger_name"]
    bet = duel["bet"]
    acceptor_name = m.from_user.full_name

    # Повторная проверка балансов
    ch_balance = get_stars(challenger_id, cid)
    ac_balance = get_stars(uid, cid)

    if ch_balance < bet or ac_balance < bet:
        await m.reply("У кого-то уже не хватает звёзд. Дуэль отменена.")
        return

    # Бросок кубиков
    roll_ch = random.randint(1, 6)
    roll_ac = random.randint(1, 6)

    if roll_ch > roll_ac:
        # Победил вызывающий
        new_ch = update_stars(challenger_id, cid, challenger_name, bet)
        new_ac = update_stars(uid, cid, acceptor_name, -bet)
        update_casino_stats(challenger_id, cid, won=bet)
        update_casino_stats(uid, cid, lost=bet)
        update_season_stat(challenger_id, cid, challenger_name, won=bet)
        update_season_stat(uid, cid, acceptor_name, lost=bet)
        add_log(cid, challenger_id, challenger_name, bet, f"кости vs {acceptor_name}")
        add_log(cid, uid, acceptor_name, -bet, f"кости vs {challenger_name}")
        await m.reply(
            f"🎲 <b>Дуэль</b>\n\n"
            f"<b>{challenger_name}</b> выбросил: {roll_ch}\n"
            f"<b>{acceptor_name}</b> выбросил: {roll_ac}\n\n"
            f"🏆 Победил <b>{challenger_name}</b>! +{bet} ⭐\n"
            f"Баланс {challenger_name}: <b>{new_ch}</b>\n"
            f"Баланс {acceptor_name}: <b>{new_ac}</b>"
        )
    elif roll_ac > roll_ch:
        new_ac = update_stars(uid, cid, acceptor_name, bet)
        new_ch = update_stars(challenger_id, cid, challenger_name, -bet)
        update_casino_stats(uid, cid, won=bet)
        update_casino_stats(challenger_id, cid, lost=bet)
        update_season_stat(uid, cid, acceptor_name, won=bet)
        update_season_stat(challenger_id, cid, challenger_name, lost=bet)
        add_log(cid, uid, acceptor_name, bet, f"кости vs {challenger_name}")
        add_log(cid, challenger_id, challenger_name, -bet, f"кости vs {acceptor_name}")
        await m.reply(
            f"🎲 <b>Дуэль</b>\n\n"
            f"<b>{challenger_name}</b> выбросил: {roll_ch}\n"
            f"<b>{acceptor_name}</b> выбросил: {roll_ac}\n\n"
            f"🏆 Победил <b>{acceptor_name}</b>! +{bet} ⭐\n"
            f"Баланс {challenger_name}: <b>{new_ch}</b>\n"
            f"Баланс {acceptor_name}: <b>{new_ac}</b>"
        )
    else:
        await m.reply(
            f"🎲 <b>Дуэль</b>\n\n"
            f"<b>{challenger_name}</b> выбросил: {roll_ch}\n"
            f"<b>{acceptor_name}</b> выбросил: {roll_ac}\n\n"
            f"🤝 <b>Ничья!</b> Никто не теряет звёзды."
        )


@dp.message(Command("отклонить"))
async def cmd_decline(m: Message):
    cid = m.chat.id
    uid = m.from_user.id
    if cid in pending_duels and uid in pending_duels[cid]:
        pending_duels[cid].pop(uid)
        await m.reply("❌ Вызов отклонён.")
    else:
        await m.reply("Тебе никто не бросал вызов.")


# ============================================================
# КРАЖА ЗВЁЗД
# ============================================================

@dp.message(Command("украсть"))
async def cmd_steal(m: Message):
    target = None
    if m.reply_to_message:
        target = m.reply_to_message.from_user
    else:
        p = (m.text or "").split(maxsplit=1)
        if len(p) >= 2 and p[1].startswith("@"):
            un = p[1].lstrip("@")
            cursor.execute("SELECT user_id, username FROM users WHERE username=? AND chat_id=?", (un, m.chat.id))
            row = cursor.fetchone()
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

    # Проверка кулдауна
    cursor.execute("""
        SELECT last_steal FROM steal_cooldowns
        WHERE thief_id=? AND target_id=? AND chat_id=?
    """, (thief_id, target.id, cid))
    r = cursor.fetchone()
    if r:
        last = datetime.fromisoformat(r[0])
        if datetime.now() - last < timedelta(hours=STEAL_COOLDOWN_HOURS):
            left = timedelta(hours=STEAL_COOLDOWN_HOURS) - (datetime.now() - last)
            h = left.seconds // 3600
            mn = (left.seconds % 3600) // 60
            await m.reply(f"⏱️ Ты уже грабил этого человека. Осталось: {h}ч {mn}м.")
            return

    target_balance = get_stars(target.id, cid)
    if target_balance < STEAL_MIN_BALANCE:
        await m.reply(f"У <b>{target.full_name}</b> меньше {STEAL_MIN_BALANCE} ⭐, грабить нечего.")
        return

    # Записываем кулдаун сразу
    cursor.execute("""
        INSERT INTO steal_cooldowns (thief_id, target_id, chat_id, last_steal)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(thief_id, target_id, chat_id) DO UPDATE SET last_steal=?
    """, (thief_id, target.id, cid, datetime.now().isoformat(), datetime.now().isoformat()))
    db.commit()

    if random.random() < STEAL_SUCCESS_CHANCE:
        amount = random.randint(STEAL_MIN_AMOUNT, STEAL_MAX_AMOUNT)
        amount = min(amount, target_balance)
        update_stars(thief_id, cid, thief_name, amount)
        new_target = update_stars(target.id, cid, target.full_name, -amount)
        add_log(cid, thief_id, thief_name, amount, f"украл у {target.full_name}")
        add_log(cid, target.id, target.full_name, -amount, f"обокрал {thief_name}")
        await m.reply(
            f"🥷 <b>Успех!</b>\n"
            f"Ты украл <b>{amount}</b> ⭐ у <b>{target.full_name}</b>.\n"
            f"У него осталось: <b>{new_target}</b> ⭐"
        )
    else:
        update_stars(thief_id, cid, thief_name, -STEAL_FAIL_PENALTY)
        await m.reply(
            f"🚨 <b>Провал!</b>\n"
            f"Тебя поймали и ты потерял <b>{STEAL_FAIL_PENALTY}</b> ⭐."
        )


# ============================================================
# ЕЖЕНЕДЕЛЬНАЯ СВОДКА (вручную)
# ============================================================

@dp.message(Command("сводка"))
async def cmd_weekly(m: Message):
    await send_weekly_report(m.chat.id)


async def send_weekly_report(chat_id: int):
    # Берём данные за прошлую неделю (предыдущий сезон)
    prev_start = get_season_start() - timedelta(days=7)
    prev_end = get_season_start()
    season = prev_start.isoformat()

    text = f"📊 <b>Сводка за неделю</b>\n"
    text += f"({prev_start.strftime('%d.%m')} — {prev_end.strftime('%d.%m')})\n\n"

    cursor.execute("""
        SELECT user_id, good_words FROM season_stats
        WHERE chat_id=? AND season_start=? AND good_words > 0
        ORDER BY good_words DESC LIMIT 3
    """, (chat_id, season))
    rows = cursor.fetchall()
    text += "✅ <b>Самые добрые:</b>\n"
    if rows:
        for i, (uid, gw) in enumerate(rows, start=1):
            try:
                mm = await bot.get_chat_member(chat_id, uid)
                name = mm.user.full_name
            except Exception:
                name = f"ID {uid}"
            text += f"  {i}. {name} — {gw} хороших слов\n"
    else:
        text += "  пусто\n"

    cursor.execute("""
        SELECT user_id, bad_words FROM season_stats
        WHERE chat_id=? AND season_start=? AND bad_words > 0
        ORDER BY bad_words DESC LIMIT 3
    """, (chat_id, season))
    rows = cursor.fetchall()
    text += "\n❌ <b>Самые злые:</b>\n"
    if rows:
        for i, (uid, bw) in enumerate(rows, start=1):
            try:
                mm = await bot.get_chat_member(chat_id, uid)
                name = mm.user.full_name
            except Exception:
                name = f"ID {uid}"
            text += f"  {i}. {name} — {bw} плохих слов\n"
    else:
        text += "  пусто\n"

    cursor.execute("""
        SELECT user_id, won, lost FROM season_stats
        WHERE chat_id=? AND season_start=? AND (won > 0 OR lost > 0)
        ORDER BY (won - lost) DESC LIMIT 3
    """, (chat_id, season))
    rows = cursor.fetchall()
    text += "\n🎰 <b>Казино:</b>\n"
    if rows:
        for i, (uid, w, l) in enumerate(rows, start=1):
            try:
                mm = await bot.get_chat_member(chat_id, uid)
                name = mm.user.full_name
            except Exception:
                name = f"ID {uid}"
            diff = w - l
            sign = "+" if diff >= 0 else ""
            text += f"  {i}. {name} — {sign}{diff}\n"
    else:
        text += "  пусто\n"

    # Топ по балансу
    cursor.execute("""
        SELECT user_id, username, stars FROM users
        WHERE chat_id=? ORDER BY stars DESC LIMIT 3
    """, (chat_id,))
    rows = cursor.fetchall()
    text += "\n⭐ <b>Топ по балансу:</b>\n"
    if rows:
        for i, (uid, un, st) in enumerate(rows, start=1):
            try:
                mm = await bot.get_chat_member(chat_id, uid)
                name = mm.user.full_name
            except Exception:
                name = un or f"ID {uid}"
            text += f"  {i}. {name} — {st} ⭐\n"
    else:
        text += "  пусто\n"

    text += "\n📅 Новый сезон стартовал!"

    try:
        await bot.send_message(chat_id, text)
    except Exception as e:
        print(f"[WEEKLY] Не смог отправить сводку в {chat_id}: {e}")


# ============================================================
# ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ============================================================

@dp.message(F.text)
async def handle_message(message: Message):
    if not message.from_user or message.from_user.is_bot:
        return

    user = message.from_user
    text = message.text or ""
    chat_id = message.chat.id
    chat_type = message.chat.type

    if chat_type in ("group", "supergroup"):
        ensure_user(user.id, chat_id, user.username or user.full_name)

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
        inc_word_stat(user.id, chat_id, user.username or user.full_name, is_good=False)
        update_season_stat(user.id, chat_id, user.username or user.full_name, bad=1)
    elif good_w:
        if plus_count_last_hour(user.id, chat_id) >= MAX_PLUS_PER_HOUR:
            return
        if plus_sum_last_day(user.id, chat_id) >= MAX_PLUS_PER_DAY:
            return
        if same_word_used_recently(user.id, chat_id, good_w, SAME_WORD_COOLDOWN_HOURS * 60):
            return
        delta = good_v
        reason = f"авто: хорошее «{good_w}» (+{good_v})"
        inc_word_stat(user.id, chat_id, user.username or user.full_name, is_good=True)
        update_season_stat(user.id, chat_id, user.username or user.full_name, good=1)
    else:
        return

    new = update_stars(user.id, chat_id, user.username or user.full_name, delta)
    add_log(chat_id, user.id, user.full_name, delta, reason)

    if DEBUG_AUTO:
        sign = "➕" if delta > 0 else "➖"
        await message.reply(
            f"{sign} <b>{user.full_name}</b>: {reason}\nБаланс: <b>{new}</b> ⭐"
        )


@dp.message(F.new_chat_members)
async def welcome(message: Message):
    for mem in message.new_chat_members:
        if mem.is_bot:
            continue
        await message.answer(
            f"👋 <b>{mem.full_name}</b>, добро пожаловать!\n\n"
            f"Свои звёзды: /профиль\nТоп: /таблица"
        )


# ============================================================
# АВТО-СВОДКА ПО ПЯТНИЦАМ
# ============================================================
async def scheduler_loop():
    """Раз в час проверяем: если наступила новая пятница и сводка не отправлена — отправляем."""
    while True:
        try:
            now = datetime.now()
            # Если сегодня пятница и время 00:00–01:00 — отправляем сводку
            if now.weekday() == 4 and now.hour == 0:
                # Проверяем, отправляли ли уже
                cursor.execute("SELECT chat_id, last_report FROM last_weekly_report")
                sent_chats = {r[0]: r[1] for r in cursor.fetchall()}

                cursor.execute("SELECT DISTINCT chat_id FROM users")
                for (cid,) in cursor.fetchall():
                    last = sent_chats.get(cid)
                    if last:
                        last_dt = datetime.fromisoformat(last)
                        if (now - last_dt) < timedelta(days=6):
                            continue
                    # Отправляем
                    try:
                        await send_weekly_report(cid)
                    except Exception as e:
                        print(f"[SCHED] Ошибка сводки в {cid}: {e}")
                    cursor.execute("""
                        INSERT INTO last_weekly_report (chat_id, last_report) VALUES (?, ?)
                        ON CONFLICT(chat_id) DO UPDATE SET last_report=?
                    """, (cid, now.isoformat(), now.isoformat()))
                    db.commit()
        except Exception as e:
            print(f"[SCHED] Ошибка планировщика: {e}")
        await asyncio.sleep(3600)  # раз в час


async def main():
    print("=" * 40)
    print("Бот Добро-Звёзды запущен!")
    print(f"Авто-звёзды: {'ВКЛ' if AUTO_STARS_ENABLED else 'ВЫКЛ'}")
    print(f"Админов: {len(load_admins())}")
    print("=" * 40)
    asyncio.create_task(scheduler_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
