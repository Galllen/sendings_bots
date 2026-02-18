import asyncio
import logging
import re
from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    UserBannedInChannelError,
    FloodWaitError,
    InviteHashInvalidError,
    InviteHashExpiredError,
    ChannelPrivateError,
    ChannelPublicGroupNaError,
    UserAlreadyParticipantError,
    YouBlockedUserError
)
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from db.base import (
    get_active_accounts,
    get_chats_paginated,
    toggle_account_status,
    is_account_session_valid,
    get_account_by_id
)
from config import config
import os

logger = logging.getLogger(__name__)


def extract_invite_hash(invite_link: str) -> str:
    """Извлекает хеш приглашения из ссылки вида https://t.me/+Abc123 или https://t.me/joinchat/Abc123"""
    invite_link = invite_link.strip()

    # Случай 1: короткая ссылка t.me/+
    match = re.search(r't\.me/\+([a-zA-Z0-9_-]+)', invite_link)
    if match:
        return match.group(1)

    # Случай 2: полная ссылка t.me/joinchat/
    match = re.search(r't\.me/joinchat/([a-zA-Z0-9_-]+)', invite_link)
    if match:
        return match.group(1)

    # Случай 3: чистый хеш без домена
    if invite_link.startswith('+'):
        return invite_link[1:]

    return invite_link


async def check_and_join_chats(account, chats):
    """
    Проверяет участие аккаунта в чатах и вступает при необходимости
    Возвращает: (успешно_вступлено, ошибки)
    """
    if not is_account_session_valid(account.session_file):
        logger.warning(f"⚠️ Сессия недоступна для {account.phone}. Деактивируем аккаунт.")
        toggle_account_status(account.id)
        return 0, [{"chat": None, "error": "Сессия недоступна"}]

    client = TelegramClient(
        account.session_file.replace('.session', ''),
        account.api_id or config.TELEGRAM_API_ID,
        account.api_hash or config.TELEGRAM_API_HASH
    )

    joined_count = 0
    errors = []

    try:
        await client.connect()

        # Проверка авторизации
        if not await client.is_user_authorized():
            raise AuthKeyUnregisteredError()

        me = await client.get_me()
        logger.debug(f"👤 Работаем с аккаунтом: {me.first_name} ({account.phone})")

        for chat in chats:
            if not chat.is_enabled:
                continue

            chat_id = str(chat.chat_id).strip()
            chat_title = chat.title or chat_id

            try:
                # === ШАГ 1: Определяем тип чата ===
                is_invite_link = any(x in chat_id.lower() for x in ['t.me/+', 't.me/joinchat', 'telegram.me/+'])
                is_username = chat_id.startswith('@') or (
                            not is_invite_link and '/' not in chat_id and not chat_id.lstrip('-').isdigit())
                is_numeric_id = chat_id.lstrip('-').isdigit()

                # === ШАГ 2: Проверяем, состоим ли мы уже в чате ===
                already_in_chat = False
                try:
                    if is_invite_link:
                        # Для приватных ссылок проверяем через хеш
                        hash = extract_invite_hash(chat_id)
                        result = await client(CheckChatInviteRequest(hash))
                        if hasattr(result, 'participants') and me.id in [p.id for p in result.participants]:
                            already_in_chat = True
                    else:
                        # Для публичных чатов/каналов
                        entity = await client.get_entity(chat_id)
                        participants = await client.get_participants(entity, limit=100)
                        if any(p.id == me.id for p in participants.users):
                            already_in_chat = True
                except Exception as e:
                    # Не критично — продолжаем попытку вступить
                    logger.debug(f"Не удалось проверить участие в {chat_title}: {e}")

                if already_in_chat:
                    logger.debug(f"✅ Аккаунт {account.phone} уже состоит в чате '{chat_title}'")
                    continue

                # === ШАГ 3: Вступаем в чат правильным методом ===
                if is_invite_link:
                    # Приватный чат по ссылке-приглашению
                    hash = extract_invite_hash(chat_id)
                    await client(ImportChatInviteRequest(hash))
                    logger.info(f"✅ Вступил в приватный чат '{chat_title}' по ссылке")

                elif is_username or is_numeric_id:
                    # Публичный чат/канал по username или ID
                    entity = await client.get_entity(chat_id)

                    # Определяем тип: канал или группа
                    if hasattr(entity, 'broadcast') and entity.broadcast:
                        # Это канал — используем JoinChannelRequest
                        await client(JoinChannelRequest(entity))
                        logger.info(f"✅ Подписался на канал '{chat_title}'")
                    else:
                        # Это группа — тоже используем JoinChannelRequest (работает для обеих сущностей)
                        await client(JoinChannelRequest(entity))
                        logger.info(f"✅ Вступил в группу '{chat_title}'")

                else:
                    errors.append({"chat": chat_title, "error": "Неподдерживаемый формат чата"})
                    logger.warning(f"⚠️ Неподдерживаемый формат чата '{chat_title}': {chat_id}")
                    continue

                joined_count += 1

                # Пауза между вступлениями (уважаем лимиты Telegram)
                await asyncio.sleep(8)  # 8 секунд — безопасный интервал

            except UserAlreadyParticipantError:
                logger.debug(f"ℹ️ Уже состою в '{chat_title}' (поймано исключение)")
                continue

            except (UserBannedInChannelError, YouBlockedUserError) as e:
                errors.append({"chat": chat_title, "error": "Забанен/заблокирован"})
                logger.warning(f"🚫 Аккаунт {account.phone} забанен в '{chat_title}': {e}")
                # Не деактивируем аккаунт — только этот чат недоступен
                continue

            except (InviteHashInvalidError, InviteHashExpiredError, ChannelPublicGroupNaError) as e:
                errors.append({"chat": chat_title, "error": "Невалидное приглашение"})
                logger.warning(f"⚠️ Невалидная ссылка для '{chat_title}': {e}")
                continue

            except ChannelPrivateError as e:
                errors.append({"chat": chat_title, "error": "Чат приватный без доступа"})
                logger.warning(f"🔒 Нет доступа к приватному чату '{chat_title}': {e}")
                continue

            except FloodWaitError as e:
                wait_time = min(e.seconds, 300)  # Максимум 5 минут
                errors.append({"chat": chat_title, "error": f"FloodWait {wait_time}с"})
                logger.warning(f"⏳ FloodWait {wait_time}с при работе с '{chat_title}'")
                await asyncio.sleep(wait_time + 5)
                continue

            except Exception as e:
                errors.append({"chat": chat_title, "error": str(e)[:60]})
                logger.error(f"❌ Ошибка при работе с '{chat_title}' для {account.phone}: {e}")
                continue

        await client.disconnect()
        return joined_count, errors

    except AuthKeyUnregisteredError:
        await client.disconnect()
        logger.error(f"🔑 Сессия недействительна для {account.phone}. Деактивируем аккаунт.")
        toggle_account_status(account.id)
        return 0, [{"chat": None, "error": "Сессия недействительна"}]

    except Exception as e:
        await client.disconnect()
        logger.exception(f"💥 Критическая ошибка для {account.phone}: {e}")
        return 0, [{"chat": None, "error": f"Критическая ошибка: {str(e)[:60]}"}]


async def periodic_membership_check():
    """Периодическая задача проверки участия в чатах"""
    logger.info("🚀 Запуск фоновой задачи проверки участия в чатах")

    while True:
        try:
            logger.info("🔍 Запуск проверки участия аккаунтов в чатах...")

            # Получаем все активные чаты
            chats, _ = get_chats_paginated(0, 1000)  # Все чаты
            active_chats = [c for c in chats if c.is_enabled]

            if not active_chats:
                logger.info("📭 Нет активных чатов для проверки")
                await asyncio.sleep(7200)  # Проверять раз в 2 часа если нет чатов
                continue

            # Получаем валидные аккаунты
            accounts = get_active_accounts()

            if not accounts:
                logger.warning("👤 Нет активных аккаунтов с валидной сессией")
                await asyncio.sleep(3600)
                continue

            logger.info(f"👥 Проверка {len(accounts)} аккаунтов для {len(active_chats)} чатов")

            for account in accounts:
                logger.debug(f"🔄 Проверка аккаунта {account.phone}")
                joined, errors = await check_and_join_chats(account, active_chats)

                if errors:
                    error_summary = "; ".join([f"{e['chat'] or 'N/A'}: {e['error']}" for e in errors[:3]])
                    logger.warning(f"⚠️ Ошибки для {account.phone}: {error_summary}")

                if joined > 0:
                    logger.info(f"🎉 Аккаунт {account.phone} вступил в {joined} новых чатов")
                else:
                    logger.debug(f"ℹ️ Аккаунт {account.phone} не требует вступления в новые чаты")

            logger.info("✅ Проверка участия завершена успешно")

            # Следующая проверка через 4-6 часов (рандом для распределения нагрузки)
            next_check = 14400 + (hash(str(accounts[0].id)) % 7200)  # 4-6 часов
            logger.info(f"⏰ Следующая проверка через {next_check // 3600}ч {(next_check % 3600) // 60}м")
            await asyncio.sleep(next_check)

        except asyncio.CancelledError:
            logger.info("🛑 Задача проверки членства остановлена")
            break

        except Exception as e:
            logger.exception(f"🔥 Критическая ошибка в периодической задаче: {e}")
            await asyncio.sleep(300)

__all__ = ['periodic_membership_check', 'check_and_join_chats']