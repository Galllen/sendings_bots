from aiogram import Router, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    FloodWaitError,
    AuthKeyUnregisteredError
)
import os
import asyncio
from config import config
from db.base import save_account, get_accounts_paginated
from bot.navigate.keyboards import accounts_list_kb

router = Router()

SESSIONS_DIR = config.SESSIONS_DIR


class AddingAccount(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()
    # ❗ Клиент НЕ хранится в состоянии — создаём заново на каждом шаге


def get_session_path(phone: str) -> str:
    """Генерирует путь к файлу сессии по номеру телефона"""
    safe_phone = phone.replace('+', '').replace(' ', '').replace('-', '')
    return os.path.join(SESSIONS_DIR, f"account_{safe_phone}.session")


@router.callback_query(lambda c: c.data == "account_add")
async def prompt_add_account(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📱 Введите номер телефона аккаунта (в формате +79991234567):\n"
        "ℹ️ Для авторизации используется официальное приложение — "
        "вам не нужно вводить API ID/API Hash."
    )
    await state.set_state(AddingAccount.waiting_for_phone)
    await callback.answer()


@router.message(AddingAccount.waiting_for_phone)
async def process_account_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip().replace(' ', '').replace('-', '')

    if not phone.startswith('+'):
        await message.answer("❌ Номер должен начинаться с '+'. Пример: +79991234567")
        return

    session_path = get_session_path(phone)

    # Создаём клиента с ГЛОБАЛЬНЫМИ данными API
    client = TelegramClient(
        session_path.replace('.session', ''),
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH
    )

    try:
        await client.connect()

        # Проверяем, не авторизован ли уже
        if await client.is_user_authorized():
            await client.disconnect()
            save_account(
                phone=phone,
                session_file=session_path,
                api_id=config.TELEGRAM_API_ID,
                api_hash=config.TELEGRAM_API_HASH,
                is_active=True
            )
            await message.answer(f"✅ Аккаунт {phone} уже авторизован!")
            accounts, total = get_accounts_paginated(0, 5)
            await message.answer("Аккаунты:", reply_markup=accounts_list_kb(accounts, 0, total))
            await state.clear()
            return

        # Отправляем код
        await client.send_code_request(phone)
        await client.disconnect()  # ❗ Отключаемся — клиент нельзя хранить в состоянии

        await state.update_data(phone=phone, session_path=session_path)
        await message.answer(
            f"📨 Код подтверждения отправлен на {phone}\n"
            "Введите код (обычно 5 цифр, можно вводить слитно):"
        )
        await state.set_state(AddingAccount.waiting_for_code)

    except FloodWaitError as e:
        await client.disconnect()
        await message.answer(f"⚠️ Слишком много запросов. Попробуйте через {e.seconds} секунд.")
        await state.clear()
    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()


@router.message(AddingAccount.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    code = message.text.replace(' ', '').replace('-', '').strip()
    data = await state.get_data()
    phone = data['phone']
    session_path = data['session_path']

    # ❗ Создаём клиент заново — не храним его в состоянии
    client = TelegramClient(
        session_path.replace('.session', ''),
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH
    )

    try:
        await client.connect()
        await client.sign_in(phone, code)

        # Проверяем 2FA
        if not await client.is_user_authorized():
            await client.disconnect()
            await state.update_data(phone=phone, session_path=session_path)
            await message.answer("🔐 Требуется пароль двухфакторной аутентификации. Введите его:")
            await state.set_state(AddingAccount.waiting_for_password)
            return

        await client.disconnect()

        save_account(
            phone=phone,
            session_file=session_path,
            api_id=config.TELEGRAM_API_ID,
            api_hash=config.TELEGRAM_API_HASH,
            is_active=True
        )

        await message.answer(f"✅ Аккаунт {phone} успешно добавлен!")
        await state.clear()

        accounts, total = get_accounts_paginated(0, 5)
        await message.answer("Аккаунты:", reply_markup=accounts_list_kb(accounts, 0, total))

    except SessionPasswordNeededError:
        await client.disconnect()
        await state.update_data(phone=phone, session_path=session_path)
        await message.answer("🔐 Требуется пароль двухфакторной аутентификации. Введите его:")
        await state.set_state(AddingAccount.waiting_for_password)

    except PhoneCodeInvalidError:
        await client.disconnect()
        await message.answer("❌ Неверный код. Попробуйте снова:")

    except FloodWaitError as e:
        await client.disconnect()
        await message.answer(f"⚠️ Слишком много попыток. Попробуйте через {e.seconds} секунд.")
        await state.clear()

    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()


@router.message(AddingAccount.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    phone = data['phone']
    session_path = data['session_path']

    client = TelegramClient(
        session_path.replace('.session', ''),
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH
    )

    try:
        await client.connect()
        await client.sign_in(password=password)
        await client.disconnect()

        save_account(
            phone=phone,
            session_file=session_path,
            api_id=config.TELEGRAM_API_ID,
            api_hash=config.TELEGRAM_API_HASH,
            is_active=True
        )

        await message.answer(f"✅ Аккаунт {phone} успешно добавлен с 2FA!")
        await state.clear()

        accounts, total = get_accounts_paginated(0, 5)
        await message.answer("Аккаунты:", reply_markup=accounts_list_kb(accounts, 0, total))

    except Exception as e:
        await client.disconnect()
        await message.answer(f"❌ Ошибка авторизации: {str(e)}\nПопробуйте снова:")