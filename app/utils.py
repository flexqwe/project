import html
import json
import os
from pathlib import Path

import requests
from django.conf import settings
from django.utils import timezone

from .achievements import check_and_unlock_achievements
from .models import Note


# Token va Chat ID kod ichida turmasin.
# Windows PowerShell yoki PyCharm Terminal orqali beriladi:
# setx TELEGRAM_BOT_TOKEN "BOT_TOKEN_BU_YERGA"
# setx TELEGRAM_CHAT_ID "7848804902"

PRIORITY_EMOJI = {
    "shoshilinch": "🔴 ❗❗",
    "muhim": "🟡 ⚠️",
    "oddiy": "🔵 ℹ️",
    "keyinroq": "⚪ 🕒",
}


REPEAT_EMOJI = {
    "none": "🚫",
    "daily": "🔁",
    "weekly": "📅",
    "monthly": "🗓️",
    "mon_fri": "📌",
    "custom_days": "🔄",
    "custom_weeks": "🔄",
}

SNOOZE_BUTTONS = [
    ("⏱ 5 daqiqadan keyin", "5m"),
    ("⏱ 15 daqiqadan keyin", "15m"),
    ("🕐 1 soatdan keyin", "1h"),
    ("🌙 Bugun kechqurun", "evening"),
]

TELEGRAM_OFFSET_FILE = Path(settings.BASE_DIR) / ".telegram_update_offset"


def get_telegram_token():
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def get_telegram_chat_id():
    return os.environ.get("TELEGRAM_CHAT_ID", "")


def safe_text(value):
    """
    Telegram HTML parse_mode ishlaganda xatolik bo'lmasligi uchun textni xavfsiz qiladi.
    """
    return html.escape(str(value or ""))


def telegram_api_url(method):
    token = get_telegram_token()
    if not token:
        return None
    return f"https://api.telegram.org/bot{token}/{method}"


def build_snooze_keyboard(note_id):
    """
    Telegram inline buttonlari.
    callback_data max 64 bayt bo'lishi kerak, shuning uchun qisqa format ishlatamiz.
    """
    keyboard = [
        [{
            "text": "✅ Bajarildi",
            "callback_data": f"complete:{note_id}",
        }]
    ]

    for label, option in SNOOZE_BUTTONS:
        keyboard.append([{
            "text": label,
            "callback_data": f"snooze:{note_id}:{option}",
        }])
    return {"inline_keyboard": keyboard}


def build_pending_keyboard(note_id):
    """Bajarilgan reminder uchun Telegramdan orqaga qaytarish tugmasi."""
    return {
        "inline_keyboard": [[{
            "text": "↩️ Kutilmoqda qilish",
            "callback_data": f"pending:{note_id}",
        }]]
    }


def send_telegram(text, reply_markup=None):
    """
    Telegram bot orqali xabar yuboradi.
    reply_markup berilsa, inline buttonlar bilan yuboradi.
    """
    chat_id = get_telegram_chat_id()
    url = telegram_api_url("sendMessage")

    if not url:
        print("TELEGRAM ERROR: TELEGRAM_BOT_TOKEN topilmadi.")
        print("Windows PowerShell yoki PyCharm Terminalga yoz:")
        print('setx TELEGRAM_BOT_TOKEN "BOT_TOKEN_BU_YERGA"')
        return False

    if not chat_id:
        print("TELEGRAM ERROR: TELEGRAM_CHAT_ID topilmadi.")
        print("Windows PowerShell yoki PyCharm Terminalga yoz:")
        print('setx TELEGRAM_CHAT_ID "7848804902"')
        return False

    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }

    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)

    try:
        response = requests.post(url, data=data, timeout=15)

        if response.ok:
            print("TELEGRAM: xabar yuborildi.")
            return True

        print("TELEGRAM ERROR STATUS:", response.status_code)
        print("TELEGRAM ERROR RESPONSE:", response.text)
        return False

    except requests.exceptions.Timeout:
        print("TELEGRAM ERROR: timeout, internet sekin yoki Telegram javob bermadi.")
        return False

    except requests.exceptions.ConnectionError:
        print("TELEGRAM ERROR: internet aloqasi yo'q.")
        return False

    except Exception as error:
        print("TELEGRAM ERROR:", error)
        return False


def move_repeating_note_to_next_date(note, now):
    """
    Takrorlanuvchi reminder yuborilgandan keyin keyingi sanaga o'tkazadi.
    Agar server bir necha kun o'chib turgan bo'lsa, hozirdan keyingi sanagacha suradi.
    """
    try:
        next_date = note.calculate_next_reminder_date(note.remind_at)
    except Exception as error:
        print("REPEAT ERROR:", error)
        note.sent = True
        note.save(update_fields=["sent"])
        return

    while next_date and next_date <= now:
        try:
            next_date = note.calculate_next_reminder_date(next_date)
        except Exception as error:
            print("REPEAT WHILE ERROR:", error)
            next_date = None
            break

    if next_date:
        note.remind_at = next_date
        note.next_reminder_date = next_date
        note.sent = False
        note.completed = False
        note.completed_at = None
        note.save(update_fields=[
            "remind_at",
            "next_reminder_date",
            "sent",
            "completed",
            "completed_at",
        ])
        print("REPEAT: keyingi reminder sanasi:", next_date)
    else:
        note.sent = True
        note.save(update_fields=["sent"])
        print("REPEAT: keyingi sana topilmadi, note sent=True bo'ldi.")


def get_note_priority_text(note):
    """
    Note priority matnini emoji bilan tayyorlaydi.
    """
    try:
        priority_display = note.get_priority_display()
    except Exception:
        priority_display = note.priority

    emoji = PRIORITY_EMOJI.get(note.priority, "ℹ️")
    return f"{emoji} <b>{safe_text(priority_display)}</b>"


def get_note_repeat_text(note):
    """
    Note repeat matnini emoji bilan tayyorlaydi.
    """
    try:
        repeat_label = note.get_repeat_label()
    except Exception:
        repeat_label = note.repeat_type

    emoji = REPEAT_EMOJI.get(note.repeat_type, "🔁")
    return f"{emoji} <b>{safe_text(repeat_label)}</b>"


def build_note_message(note):
    """
    Telegramga yuboriladigan reminder xabarini tayyorlaydi.
    """
    priority_text = get_note_priority_text(note)
    repeat_text = get_note_repeat_text(note)

    message = (
        "⏰ <b>Eslatma vaqti keldi!</b>\n\n"
        f"📌 <b>{safe_text(note.text)}</b>\n"
        f"📍 Muhimligi: {priority_text}\n"
        f"🔁 Takrorlanish: {repeat_text}\n"
        f"📌 Status: <b>{safe_text(note.status_label)}</b>"
    )

    if note.description:
        message += f"\n📝 Eslatma info: {safe_text(note.description)}"

    try:
        local_time = timezone.localtime(note.remind_at)
        message += f"\n\n🕒 Vaqti: <b>{safe_text(local_time.strftime('%d.%m.%Y %H:%M'))}</b>"
    except Exception:
        pass

    if note.snoozed_count:
        message += f"\n😴 Snooze soni: <b>{note.snoozed_count}</b>"

    message += "\n\n👇 Kerak bo'lsa, tugmalardan foydalaning:"
    return message


def check_notes():
    """
    Vaqti kelgan reminderlarni tekshiradi va Telegramga inline snooze buttonlari bilan yuboradi.
    Bu funksiya scheduler, command yoki thread orqali chaqiriladi.
    """
    now = timezone.localtime(timezone.now())

    notes = Note.objects.filter(
        sent=False,
        completed=False,
        remind_at__lte=now,
    ).order_by("remind_at")

    if not notes.exists():
        print("REMINDER: yuboriladigan eslatma yo'q.")
        return

    for note in notes:
        message = build_note_message(note)
        sent_success = send_telegram(message, reply_markup=build_snooze_keyboard(note.id))

        if not sent_success:
            print(f"REMINDER ERROR: note id={note.id} yuborilmadi.")
            continue

        try:
            if note.is_repeating:
                move_repeating_note_to_next_date(note, now)
            else:
                note.sent = True
                note.save(update_fields=["sent"])
                print(f"REMINDER: note id={note.id} sent=True bo'ldi.")
        except Exception as error:
            print(f"REMINDER SAVE ERROR note id={note.id}:", error)


def send_test_message():
    """
    Telegram ishlayaptimi yoki yo'qmi tekshirish uchun.
    """
    text = (
        "✅ <b>Telegram bot ishlayapti!</b>\n\n"
        "Smart Note loyihasi Telegram bilan ulandi."
    )
    return send_telegram(text)


def _read_telegram_offset():
    try:
        if TELEGRAM_OFFSET_FILE.exists():
            value = TELEGRAM_OFFSET_FILE.read_text(encoding="utf-8").strip()
            return int(value) if value else None
    except Exception as error:
        print("TELEGRAM OFFSET READ ERROR:", error)
    return None


def _write_telegram_offset(offset):
    try:
        TELEGRAM_OFFSET_FILE.write_text(str(offset), encoding="utf-8")
    except Exception as error:
        print("TELEGRAM OFFSET WRITE ERROR:", error)


def answer_callback_query(callback_query_id, text, show_alert=False):
    url = telegram_api_url("answerCallbackQuery")
    if not url or not callback_query_id:
        return False

    try:
        response = requests.post(url, data={
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": "true" if show_alert else "false",
        }, timeout=10)
        return response.ok
    except Exception as error:
        print("TELEGRAM CALLBACK ANSWER ERROR:", error)
        return False


def edit_telegram_message(chat_id, message_id, text, reply_markup=None):
    url = telegram_api_url("editMessageText")
    if not url or not chat_id or not message_id:
        return False

    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
    }

    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)

    try:
        response = requests.post(url, data=data, timeout=10)
        if not response.ok:
            print("TELEGRAM EDIT ERROR:", response.text)
        return response.ok
    except Exception as error:
        print("TELEGRAM EDIT EXCEPTION:", error)
        return False


def build_snoozed_callback_message(note, new_time, option):
    local_new_time = timezone.localtime(new_time)
    option_label = note.get_snooze_label(option)

    return (
        "😴 <b>Reminder snooze qilindi!</b>\n\n"
        f"📌 <b>{safe_text(note.text)}</b>\n"
        f"⏳ Tanlov: <b>{safe_text(option_label)}</b>\n"
        f"🕒 Yangi vaqt: <b>{safe_text(local_new_time.strftime('%d.%m.%Y %H:%M'))}</b>\n"
        f"📌 Status: <b>Kutilmoqda</b>\n"
        f"🔢 Snooze soni: <b>{note.snoozed_count}</b>"
    )


def build_completed_callback_message(note, unlocked_achievements=None):
    completed_at = timezone.localtime(note.completed_at or timezone.now())

    message = (
        "✅ <b>Reminder bajarildi!</b>\n\n"
        f"📌 <b>{safe_text(note.text)}</b>\n"
        f"📌 Status: <b>Bajarildi</b>\n"
        f"🏁 Bajarilgan vaqt: <b>{safe_text(completed_at.strftime('%d.%m.%Y %H:%M'))}</b>"
    )

    if unlocked_achievements:
        message += "\n\n🏆 <b>Yangi achievement ochildi!</b>"
        for badge in unlocked_achievements:
            message += f"\n{safe_text(badge.get('icon', '🏆'))} <b>{safe_text(badge.get('title'))}</b>"

    return message


def build_pending_callback_message(note):
    return (
        "↩️ <b>Reminder qayta kutilmoqda holatiga qaytarildi!</b>\n\n"
        f"📌 <b>{safe_text(note.text)}</b>\n"
        f"📌 Status: <b>Kutilmoqda</b>"
    )


def _is_allowed_callback_owner(callback_query):
    message = callback_query.get("message") or {}
    message_chat = (message.get("chat") or {}).get("id")
    configured_chat_id = get_telegram_chat_id()
    return not configured_chat_id or str(message_chat) == str(configured_chat_id)


def handle_complete_callback(callback_query):
    callback_id = callback_query.get("id")
    data = callback_query.get("data", "")
    message = callback_query.get("message") or {}

    parts = data.split(":")
    if len(parts) != 2 or parts[0] != "complete":
        answer_callback_query(callback_id, "Noma'lum callback.", show_alert=True)
        return

    if not _is_allowed_callback_owner(callback_query):
        answer_callback_query(callback_id, "Bu bot faqat egasi uchun ishlaydi.", show_alert=True)
        return

    try:
        note_id = int(parts[1])
    except ValueError:
        answer_callback_query(callback_id, "Reminder ID xato.", show_alert=True)
        return

    try:
        note = Note.objects.get(id=note_id)
    except Note.DoesNotExist:
        answer_callback_query(callback_id, "Bu reminder topilmadi yoki o'chirilgan.", show_alert=True)
        return

    note.mark_completed()
    note.refresh_from_db()
    unlocked_achievements = check_and_unlock_achievements()

    if unlocked_achievements:
        answer_text = "Yangi achievement ochildi 🏆"
    else:
        answer_text = "Reminder bajarildi deb belgilandi ✅"
    answer_callback_query(callback_id, answer_text, show_alert=False)

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    edit_telegram_message(
        chat_id,
        message_id,
        build_completed_callback_message(note, unlocked_achievements),
        reply_markup=build_pending_keyboard(note.id),
    )

    print(f"TELEGRAM CALLBACK: note id={note.id} completed=True")


def handle_pending_callback(callback_query):
    callback_id = callback_query.get("id")
    data = callback_query.get("data", "")
    message = callback_query.get("message") or {}

    parts = data.split(":")
    if len(parts) != 2 or parts[0] != "pending":
        answer_callback_query(callback_id, "Noma'lum callback.", show_alert=True)
        return

    if not _is_allowed_callback_owner(callback_query):
        answer_callback_query(callback_id, "Bu bot faqat egasi uchun ishlaydi.", show_alert=True)
        return

    try:
        note_id = int(parts[1])
    except ValueError:
        answer_callback_query(callback_id, "Reminder ID xato.", show_alert=True)
        return

    try:
        note = Note.objects.get(id=note_id)
    except Note.DoesNotExist:
        answer_callback_query(callback_id, "Bu reminder topilmadi yoki o'chirilgan.", show_alert=True)
        return

    note.mark_pending()
    note.refresh_from_db()

    answer_callback_query(callback_id, "Reminder kutilmoqda holatiga qaytarildi ↩️", show_alert=False)

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    edit_telegram_message(
        chat_id,
        message_id,
        build_pending_callback_message(note),
        reply_markup=build_snooze_keyboard(note.id),
    )

    print(f"TELEGRAM CALLBACK: note id={note.id} completed=False")


def handle_snooze_callback(callback_query):
    callback_id = callback_query.get("id")
    data = callback_query.get("data", "")
    message = callback_query.get("message") or {}

    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "snooze":
        answer_callback_query(callback_id, "Noma'lum callback.", show_alert=True)
        return

    message_chat = (message.get("chat") or {}).get("id")
    configured_chat_id = get_telegram_chat_id()
    if configured_chat_id and str(message_chat) != str(configured_chat_id):
        answer_callback_query(callback_id, "Bu bot faqat egasi uchun ishlaydi.", show_alert=True)
        return

    try:
        note_id = int(parts[1])
    except ValueError:
        answer_callback_query(callback_id, "Reminder ID xato.", show_alert=True)
        return

    option = parts[2]
    if option not in {"5m", "15m", "1h", "evening"}:
        option = "5m"

    try:
        note = Note.objects.get(id=note_id)
    except Note.DoesNotExist:
        answer_callback_query(callback_id, "Bu reminder topilmadi yoki o'chirilgan.", show_alert=True)
        return

    new_time = note.snooze(option)
    note.refresh_from_db()

    local_new_time = timezone.localtime(new_time)
    answer_callback_query(
        callback_id,
        f"Snooze qilindi: {local_new_time.strftime('%d.%m.%Y %H:%M')}",
        show_alert=False,
    )

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    edit_telegram_message(
        chat_id,
        message_id,
        build_snoozed_callback_message(note, new_time, option),
    )

    print(f"TELEGRAM CALLBACK: note id={note.id} snooze -> {local_new_time}")


def check_telegram_callbacks():
    """
    Telegram inline button callbacklarini polling orqali tekshiradi.
    Webhook kerak emas: runserver ishlaganda background thread buni chaqiradi.
    """
    url = telegram_api_url("getUpdates")
    if not url:
        return

    params = {
        "timeout": 1,
        "allowed_updates": json.dumps(["callback_query"]),
    }

    offset = _read_telegram_offset()
    if offset is not None:
        params["offset"] = offset

    try:
        response = requests.get(url, params=params, timeout=8)
        if not response.ok:
            print("TELEGRAM GETUPDATES ERROR:", response.text)
            return

        payload = response.json()
        updates = payload.get("result", [])

        if not updates:
            return

        next_offset = None
        for update in updates:
            update_id = update.get("update_id")
            if update_id is not None:
                next_offset = max(next_offset or 0, update_id + 1)

            callback_query = update.get("callback_query")
            if callback_query:
                data = callback_query.get("data", "")
                if data.startswith("snooze:"):
                    handle_snooze_callback(callback_query)
                elif data.startswith("complete:"):
                    handle_complete_callback(callback_query)
                elif data.startswith("pending:"):
                    handle_pending_callback(callback_query)
                else:
                    answer_callback_query(
                        callback_query.get("id"),
                        "Noma'lum callback.",
                        show_alert=True,
                    )

        if next_offset is not None:
            _write_telegram_offset(next_offset)

    except requests.exceptions.Timeout:
        return
    except requests.exceptions.ConnectionError:
        print("TELEGRAM CALLBACK ERROR: internet aloqasi yo'q.")
    except Exception as error:
        print("TELEGRAM CALLBACK ERROR:", error)
