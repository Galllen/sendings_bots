from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
from db.base import is_account_session_valid

MAX_BUTTON_TEXT_LENGTH = 30


def truncate(text, max_len=MAX_BUTTON_TEXT_LENGTH):
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def main_menu_kb():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📃 Сообщения", callback_data="messages:start:0")],
        [InlineKeyboardButton(text="👤 Аккаунты", callback_data="accounts:start:0")],
        [InlineKeyboardButton(text="💬 Чаты", callback_data="chats:start:0")],
        [InlineKeyboardButton(text="📤 Отправления", callback_data="broadcast_history:start:0")]
    ])
    return keyboard


def reply_menu_kb():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="/start", callback_data="start")]
    ])
    return keyboard


def messages_list_kb(messages, offset, total):
    keyboard = []
    for msg in messages:
        status_icon = "✅" if msg.is_enabled else "🚫"
        name = truncate(msg.name)
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status_icon} {msg.id}. {name}",
                callback_data=f"message:{msg.id}"
            )
        ])

    nav_buttons = []
    limit = 5
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"messages:start:{offset - limit}"))
    if offset + limit < total:
        nav_buttons.append(InlineKeyboardButton(text="Далее ▶️", callback_data=f"messages:start:{offset + limit}"))

    action_buttons = [
        InlineKeyboardButton(text="➕ Добавить", callback_data="message_add"),
        InlineKeyboardButton(text="🔙 Назад к меню", callback_data="main_menu")
    ]

    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append(action_buttons)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def message_detail_kb(msg_id: int, is_enabled: bool):
    status_btn_text = "🔴 Деактивировать" if is_enabled else "🟢 Активировать"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status_btn_text, callback_data=f"toggle_message_status:{msg_id}")],
        [InlineKeyboardButton(text="📎 Привязать чаты", callback_data=f"link_chats:{msg_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"del_message:{msg_id}")],
        [InlineKeyboardButton(text="🔙 Назад к меню", callback_data="main_menu")]
    ])
    return kb


def link_chats_kb(msg_id: int):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"message:{msg_id}")]
    ])
    return kb


def accounts_list_kb(accounts, offset, total):
    keyboard = []
    for acc in accounts:
        session_valid = is_account_session_valid(acc.session_file)

        if not acc.is_active:
            status_icon = "🔴"
        elif not session_valid:
            status_icon = "⚠️"
        else:
            status_icon = "✅"

        phone = truncate(acc.phone)
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status_icon} {phone}",
                callback_data=f"account:{acc.id}"
            )
        ])

    nav_buttons = []
    limit = 5
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"accounts:start:{offset - limit}"))
    if offset + limit < total:
        nav_buttons.append(InlineKeyboardButton(text="Далее ▶️", callback_data=f"accounts:start:{offset + limit}"))

    action_buttons = [
        InlineKeyboardButton(text="➕ Добавить", callback_data="account_add"),
        InlineKeyboardButton(text="🔙 Назад к меню", callback_data="main_menu")
    ]

    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append(action_buttons)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def account_detail_kb(acc_id: int, is_active: bool, session_valid: bool):
    keyboard = []

    if not session_valid:
        keyboard.append([
            InlineKeyboardButton(
                text="🔄 Повторить авторизацию",
                callback_data=f"reauth_account:{acc_id}"
            )
        ])

    status_btn_text = "🔴 Деактивировать" if is_active else "🟢 Активировать"
    keyboard.append([
        InlineKeyboardButton(text=status_btn_text, callback_data=f"toggle_account:{acc_id}")
    ])
    keyboard.append([
        InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"del_account:{acc_id}")
    ])
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_accounts")
    ])
    keyboard.append([
        InlineKeyboardButton(text="🔙 Назад к меню", callback_data="main_menu")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def chats_list_kb(chats, offset, total):
    keyboard = []
    for chat in chats:
        status_icon = "✅" if chat.is_enabled else "🚫"
        title = truncate(chat.title or "Без названия")
        chat_id = truncate(str(chat.chat_id))
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status_icon} {title} ({chat_id})",
                callback_data=f"chat:{chat.id}"
            )
        ])

    nav_buttons = []
    limit = 5
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"chats:start:{offset - limit}"))
    if offset + limit < total:
        nav_buttons.append(InlineKeyboardButton(text="Далее ▶️", callback_data=f"chats:start:{offset + limit}"))

    action_buttons = [
        InlineKeyboardButton(text="➕ Добавить", callback_data="chat_add"),
        InlineKeyboardButton(text="🔙 Назад к меню", callback_data="main_menu")
    ]

    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append(action_buttons)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def chat_detail_kb(chat_id: int, is_enabled: bool):
    status_btn_text = "🔴 Деактивировать" if is_enabled else "🟢 Активировать"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status_btn_text, callback_data=f"toggle_chat:{chat_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"del_chat:{chat_id}")],
        [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_chats")],
        [InlineKeyboardButton(text="🔙 Назад к меню", callback_data="main_menu")]
    ])
    return kb

def chats_list_kb_for_history(chats, offset, total):
    keyboard = []
    for chat in chats:
        title = truncate(chat.title or "Без названия")
        chat_id = truncate(str(chat.chat_id))
        keyboard.append([
            InlineKeyboardButton(
                text=f"{title} ({chat_id})",
                callback_data=f"chat_history:{chat.id}"
            )
        ])

    nav_buttons = []
    limit = 5
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=f"broadcast_history:start:{offset - limit}"
        ))
    if offset + limit < total:
        nav_buttons.append(InlineKeyboardButton(
            text="Далее ▶️",
            callback_data=f"broadcast_history:start:{offset + limit}"
        ))

    action_buttons = [
        InlineKeyboardButton(text="🔙 Назад к меню", callback_data="main_menu")
    ]

    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append(action_buttons)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def back_to_history_menu_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к списку чатов", callback_data="back_to_broadcast_history")],
        [InlineKeyboardButton(text="🔙 Назад к меню", callback_data="main_menu")]
    ])
    return kb