import asyncio
import logging
import random
import re
import os
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    UserBannedInChannelError,
    ChannelPrivateError,
    InviteHashInvalidError,
    YouBlockedUserError,
    PeerIdInvalidError, InviteHashExpiredError
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from db.model import Message, Account, Chat, SentHistory, DailyStats  # ← КРИТИЧЕСКИ ВАЖНО: импорт моделей
from db.base import (
    get_db,
    get_active_accounts,
    get_chats_by_message_id,
    is_account_session_valid,
    toggle_account_status
)
from config import config

logger = logging.getLogger(__name__)

# Глобальные локи для защиты сессий
_SESSION_LOCKS = {}


def get_session_lock(session_file: str) -> asyncio.Lock:
    """Возвращает уникальный лок для файла сессии"""
    if session_file not in _SESSION_LOCKS:
        _SESSION_LOCKS[session_file] = asyncio.Lock()
    return _SESSION_LOCKS[session_file]


def extract_invite_hash(invite_link: str) -> str:
    """Извлекает хеш приглашения из ссылки"""
    invite_link = invite_link.strip()
    match = re.search(r't\.me/\+([a-zA-Z0-9_-]+)', invite_link)
    if match:
        return match.group(1)
    match = re.search(r't\.me/joinchat/([a-zA-Z0-9_-]+)', invite_link)
    if match:
        return match.group(1)
    if invite_link.startswith('+'):
        return invite_link[1:]
    return invite_link


async def ensure_chat_membership(client, chat_id: str, account_phone: str) -> bool:
    """Проверяет и при необходимости вступает в чат"""
    try:
        chat_id = chat_id.strip()
        is_invite_link = any(x in chat_id.lower() for x in ['t.me/+', 't.me/joinchat', 'telegram.me/+'])

        if is_invite_link:
            hash = extract_invite_hash(chat_id)
            try:
                result = await client(CheckChatInviteRequest(hash))
                if hasattr(result, 'participants'):
                    me = await client.get_me()
                    if any(p.id == me.id for p in result.participants):
                        return True
            except Exception:
                pass

            await client(ImportChatInviteRequest(hash))
            logger.info(f"✅ Аккаунт {account_phone} вступил в приватный чат по ссылке")
            return True

        else:
            entity = await client.get_entity(chat_id)
            try:
                participants = await client.get_participants(entity, limit=100)
                me = await client.get_me()
                if any(p.id == me.id for p in participants.users):
                    return True
            except Exception:
                pass

            await client(JoinChannelRequest(entity))
            logger.info(f"✅ Аккаунт {account_phone} вступил в публичный чат {chat_id}")
            return True

    except (UserBannedInChannelError, YouBlockedUserError):
        logger.warning(f"🚫 Аккаунт {account_phone} забанен в чате {chat_id}")
        return False
    except (InviteHashInvalidError, InviteHashExpiredError, ChannelPrivateError):
        logger.warning(f"⚠️ Нет доступа к чату {chat_id} для аккаунта {account_phone}")
        return False
    except FloodWaitError as e:
        wait_time = min(e.seconds, 300)
        logger.warning(f"⏳ FloodWait {wait_time}с при вступлении в {chat_id}")
        await asyncio.sleep(wait_time)
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при работе с чатом {chat_id}: {e}")
        return False


async def send_message_with_account(account, chat_id: str, message_content: str) -> tuple[bool, str]:
    """Отправляет сообщение через аккаунт с полной обработкой ошибок"""
    if not is_account_session_valid(account.session_file):
        logger.warning(f"⚠️ Сессия недоступна для {account.phone}. Деактивируем аккаунт.")
        toggle_account_status(account.id)
        return False, "Сессия недоступна"

    # 🔒 Захватываем лок для этой сессии
    session_lock = get_session_lock(account.session_file)
    async with session_lock:
        client = TelegramClient(
            account.session_file.replace('.session', ''),
            account.api_id or config.TELEGRAM_API_ID,
            account.api_hash or config.TELEGRAM_API_HASH
        )

        try:
            await client.connect()

            if not await client.is_user_authorized():
                raise AuthKeyUnregisteredError()

            # Проверяем/вступаем в чат
            if not await ensure_chat_membership(client, chat_id, account.phone):
                await client.disconnect()
                return False, "Не удалось вступить в чат"

            # Отправляем сообщение
            await client.send_message(chat_id, message_content)
            await client.disconnect()

            logger.info(f"📤 Успешно отправлено в {chat_id} через {account.phone}")
            return True, "Успешно отправлено"

        except AuthKeyUnregisteredError:
            await client.disconnect()
            logger.error(f"🔑 Сессия недействительна для {account.phone}. Деактивируем аккаунт.")
            toggle_account_status(account.id)
            return False, "Сессия недействительна"

        except FloodWaitError as e:
            await client.disconnect()
            wait_time = min(e.seconds, 300)
            logger.warning(f"⏳ FloodWait {wait_time}с для {account.phone} при отправке в {chat_id}")
            await asyncio.sleep(wait_time)
            return False, f"FloodWait {wait_time}с"

        except (UserBannedInChannelError, YouBlockedUserError):
            await client.disconnect()
            logger.warning(f"🚫 Аккаунт {account.phone} забанен в {chat_id}")
            return False, "Забанен в чате"

        except PeerIdInvalidError:
            await client.disconnect()
            logger.warning(f"⚠️ Неверный ID чата {chat_id}")
            return False, "Неверный ID чата"

        except Exception as e:
            await client.disconnect()
            error_msg = str(e)[:100]
            logger.error(f"❌ Ошибка отправки в {chat_id} через {account.phone}: {error_msg}")
            return False, f"Ошибка: {error_msg}"


def get_messages_due_for_sending():
    """Возвращает сообщения, готовые к отправке (поддержка дробных интервалов)"""
    db = next(get_db())
    try:
        messages = db.query(Message).filter(Message.is_enabled == True).all()
        due_messages = []

        for msg in messages:
            # Теперь интервал в часах может быть дробным (0.1 = 6 минут)
            interval_timedelta = timedelta(hours=float(msg.interval_hours))

            last_sent = db.query(SentHistory) \
                .filter(SentHistory.message_id == msg.id) \
                .order_by(SentHistory.sent_at.desc()) \
                .first()

            if last_sent is None or (datetime.utcnow() - last_sent.sent_at > interval_timedelta):
                due_messages.append(msg)

        return due_messages
    finally:
        db.close()


async def distribute_and_send_messages():
    """Распределяет чаты между аккаунтами и отправляет сообщения"""
    logger.info("🚀 Запуск цикла отправки сообщений...")

    # Получаем сообщения, готовые к отправке
    due_messages = get_messages_due_for_sending()

    if not due_messages:
        logger.info("📭 Нет сообщений, готовых к отправке")
        return

    logger.info(f"📬 Найдено {len(due_messages)} сообщений для отправки")

    # Получаем активные аккаунты
    accounts = get_active_accounts()

    if not accounts:
        logger.warning("👤 Нет активных аккаунтов с валидной сессией")
        return

    logger.info(f"👥 Используем {len(accounts)} активных аккаунтов")

    # Отправляем каждое сообщение
    for message in due_messages:
        chats = get_chats_by_message_id(message.id)
        active_chats = [c for c in chats if c.is_enabled]

        if not active_chats:
            logger.info(f"📭 У сообщения '{message.name}' нет активных чатов")
            continue

        logger.info(
            f"📨 Отправка сообщения '{message.name}' (интервал: {message.interval_hours}ч) в {len(active_chats)} чатов")

        # Распределяем чаты между аккаунтами (раунд-робин)
        for i, chat in enumerate(active_chats):
            account = accounts[i % len(accounts)]  # Циклическое распределение

            logger.debug(f"🔄 Отправка в {chat.title or chat.chat_id} через {account.phone}")

            success, result = await send_message_with_account(
                account,
                chat.chat_id,
                message.content
            )

            # Записываем в историю
            db = next(get_db())
            try:
                history = SentHistory(
                    account_id=account.id,
                    message_id=message.id,
                    chat_id=chat.id,
                    status='success' if success else 'failed',
                    error_message=None if success else result
                )
                db.add(history)
                db.commit()
            finally:
                db.close()

            # Обновляем статистику
            await update_daily_stats(account.id, success)

            # Пауза между отправками (2-4 сек для соблюдения лимитов)
            await asyncio.sleep(random.uniform(2.0, 4.0))

        logger.info(f"✅ Сообщение '{message.name}' отправлено во все чаты")

    logger.info("🏁 Цикл отправки завершён")


async def update_daily_stats(account_id: int, success: bool):
    db = next(get_db())
    try:
        today = datetime.utcnow().date()
        stats = db.query(DailyStats) \
            .filter(DailyStats.account_id == account_id) \
            .filter(DailyStats.date == today) \
            .first()

        if not stats:
            stats = DailyStats(account_id=account_id, date=today)
            db.add(stats)

        if success:
            stats.successful_count += 1
        else:
            stats.failed_count += 1

        db.commit()
    finally:
        db.close()


async def periodic_broadcast():
    """
    Фоновая задача периодической отправки сообщений
    Запускается каждые 5 минут для проверки готовых к отправке сообщений
    """
    logger.info("⏰ Запуск фоновой задачи периодической отправки")

    while True:
        try:
            await distribute_and_send_messages()

            # Следующая проверка через 5 минут
            await asyncio.sleep(300)

        except asyncio.CancelledError:
            logger.info("🛑 Задача периодической отправки остановлена")
            break

        except Exception as e:
            logger.exception(f"🔥 Критическая ошибка в задаче отправки: {e}")
            await asyncio.sleep(60)  # Пауза 1 минута перед повтором