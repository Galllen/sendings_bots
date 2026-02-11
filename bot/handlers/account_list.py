from aiogram import Router, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from bot.navigate.keyboards import accounts_list_kb, account_detail_kb, main_menu_kb
from db.base import get_accounts_paginated, get_account_by_id, toggle_account_status, save_account

router = Router()

# === Обработчики списка и деталей ===

@router.callback_query(lambda c: c.data.startswith("accounts:"))
async def show_accounts(callback: types.CallbackQuery):
    _, _, offset_str = callback.data.split(":")
    offset = int(offset_str)
    limit = 5
    accounts, total = get_accounts_paginated(offset, limit)
    kb = accounts_list_kb(accounts, offset, total)
    await callback.message.edit_text("Аккаунты:", reply_markup=kb)
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("account:"))
async def show_account_detail(callback: types.CallbackQuery):
    acc_id = int(callback.data.split(":")[1])
    acc = get_account_by_id(acc_id)
    if not acc:
        await callback.answer("Аккаунт не найден.", show_alert=True)
        return

    status = "активен" if acc.is_active else "деактивирован"
    text = f"""
Телефон: {acc.phone}
Сессия: {acc.session_file}
API ID: {acc.api_id}
Статус: {status}
    """.strip()

    await callback.message.edit_text(text, reply_markup=account_detail_kb(acc.id, acc.is_active))
    await callback.answer()

@router.callback_query(lambda c: c.data.startswith("toggle_account:"))
async def toggle_account_status_handler(callback: types.CallbackQuery):
    acc_id = int(callback.data.split(":")[1])
    new_status = toggle_account_status(acc_id)
    status_text = "активирован" if new_status else "деактивирован"
    await callback.answer(f"Аккаунт {status_text}.", show_alert=True)
    # Обновим сообщение
    acc = get_account_by_id(acc_id)
    text = f"""
Телефон: {acc.phone}
Сессия: {acc.session_file}
API ID: {acc.api_id}
Статус: {'активен' if acc.is_active else 'деактивирован'}
    """.strip()
    await callback.message.edit_text(text, reply_markup=account_detail_kb(acc.id, acc.is_active))

@router.callback_query(lambda c: c.data == "back_to_accounts")
async def back_to_accounts(callback: types.CallbackQuery):
    offset = 0
    accounts, total = get_accounts_paginated(offset, 5)
    kb = accounts_list_kb(accounts, offset, total)
    await callback.message.edit_text("Аккаунты:", reply_markup=kb)
    await callback.answer()

@router.callback_query(lambda c: c.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите действие:", reply_markup=main_menu_kb())
    await callback.answer()


class AddingAccount(StatesGroup):
    waiting_for_phone = State()
    waiting_for_session = State()

@router.callback_query(lambda c: c.data == "account_add")
async def prompt_add_account(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите номер телефона аккаунта:")
    await state.set_state(AddingAccount.waiting_for_phone)

@router.message(AddingAccount.waiting_for_phone)
async def process_account_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Введите путь к файлу сессии (session_file):")
    await state.set_state(AddingAccount.waiting_for_session)

@router.message(AddingAccount.waiting_for_session)
async def finish_add_account(message: types.Message, state: FSMContext):
    data = await state.get_data()
    phone = data.get("phone")
    session_file = message.text

    save_account(phone, session_file)

    await message.answer(f"Аккаунт {phone} добавлен!")
    await state.clear()

    offset = 0
    accounts, total = get_accounts_paginated(offset, 5)
    kb = accounts_list_kb(accounts, offset, total)
    await message.answer("Аккаунты:", reply_markup=kb)