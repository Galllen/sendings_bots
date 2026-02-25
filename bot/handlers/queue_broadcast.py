import asyncio
import logging
import random
from datetime import datetime, timedelta

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    UserBannedInChannelError,
    YouBlockedUserError,
    PeerIdInvalidError
)

from db.base import (
    get_active_queues,
    get_queue_messages,
    get_queue_chats,
    get_active_accounts,
    toggle_account_status,
    is_account_session_valid,
    get_db
)
from db.model import SentHistory
from config import config

logger = logging.getLogger(__name__)

_SESSION_LOCKS = {}


def get_session_lock(session_file: str) -> asyncio.Lock:
    if session_file not in _SESSION_LOCKS:
        _SESSION_LOCKS[session_file] = asyncio.Lock()
    return _SESSION_LOCKS[session_file]


async def send_message_with_account(account, chat_id: str, message_content: str) -> tuple[bool, str]:

    if not is_account_session_valid(account.session_file):
        logger.warning(f"⚠️ Сессия недоступна для {account.phone}. Деактивируем аккаунт.")
        toggle_account_status(account.id)
        return False, "Сессия недоступна"

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

            entity = await client.get_entity(chat_id)
            await client.send_message(entity, message_content)
            await client.disconnect()
            return True, ""

        except AuthKeyUnregisteredError:
            await client.disconnect()
            logger.error(f"🔑 Сессия недействительна для {account.phone}. Деактивируем.")
            toggle_account_status(account.id)
            return False, "Сессия недействительна"

        except FloodWaitError as e:
            await client.disconnect()
            wait_time = min(e.seconds, 300)
            logger.warning(f"⏳ FloodWait {wait_time}с для {account.phone}")
            await asyncio.sleep(wait_time)
            return False, f"FloodWait {wait_time}с"

        except (UserBannedInChannelError, YouBlockedUserError):
            await client.disconnect()
            logger.warning(f"🚫 Аккаунт {account.phone} забанен в чате")
            return False, "Забанен в чате"

        except PeerIdInvalidError:
            await client.disconnect()
            logger.warning(f"⚠️ Неверный ID чата {chat_id}")
            return False, "Неверный ID чата"

        except ValueError as e:
            # Например, неверный формат chat_id
            await client.disconnect()
            logger.warning(f"⚠️ Некорректный chat_id {chat_id}: {e}")
            return False, f"Некорректный chat_id"

        except Exception as e:
            await client.disconnect()
            error_msg = str(e)[:100]
            logger.error(f"❌ Ошибка отправки через {account.phone}: {error_msg}")
            return False, f"Ошибка: {error_msg}"


async def rotate_queue_order(queue_id: int):
    db = next(get_db())
    try:
        from db.model import QueueMessage
        qms = db.query(QueueMessage).filter(QueueMessage.queue_id == queue_id).order_by(QueueMessage.position).all()
        if not qms:
            return
        n = len(qms)
        new_positions = {}
        for i, qm in enumerate(qms):
            new_pos = (i + 1) % n
            new_positions[qm.id] = new_pos
        for qm_id, pos in new_positions.items():
            db.query(QueueMessage).filter(QueueMessage.id == qm_id).update({"position": pos})
        db.commit()
        logger.debug(f"Очередь {queue_id}: порядок сообщений изменён")
    except Exception as e:
        logger.error(f"Ошибка ротации очереди {queue_id}: {e}")
    finally:
        db.close()


async def process_queue(queue):
    now = datetime.now()
    today = now.date()

    try:
        start_time = datetime.strptime(queue.time_start, "%H:%M").time()
        end_time = datetime.strptime(queue.time_end, "%H:%M").time()
    except ValueError:
        logger.error(f"Неверный формат времени в очереди {queue.id}: {queue.time_start}-{queue.time_end}")
        return

    if not (start_time <= now.time() <= end_time):
        return

    if queue.last_sent_date is None or queue.last_sent_date.date() < today:
        await rotate_queue_order(queue.id)
        queue.current_index = 0
        queue.last_sent_date = now

    messages = get_queue_messages(queue.id)
    if not messages:
        logger.warning(f"Очередь {queue.id} не содержит сообщений")
        return

    total_messages = len(messages)
    if queue.current_index >= total_messages:
        logger.debug(f"Очередь {queue.id} завершила круг на сегодня")
        return

    if queue.last_sent_at:
        random_offset = random.uniform(-15, 15) * 60
        next_time = queue.last_sent_at + timedelta(minutes=queue.interval_minutes) + timedelta(seconds=random_offset)
        if now < next_time:
            return

    current_message = messages[queue.current_index]
    chats = get_queue_chats(queue.id)
    if not chats:
        logger.warning(f"Очередь {queue.id} не содержит чатов")
        return

    accounts = get_active_accounts()
    if not accounts:
        logger.warning("Нет активных аккаунтов для отправки")
        return

    success_count = 0
    fail_count = 0

    for chat in chats:
        sent = False
        last_error = ""
        shuffled_accounts = random.sample(accounts, len(accounts))
        for account in shuffled_accounts:
            success, error = await send_message_with_account(account, chat.chat_id, current_message.content)
            if success:
                sent = True
                success_count += 1
                db = next(get_db())
                try:
                    history = SentHistory(
                        account_id=account.id,
                        message_id=current_message.id,
                        chat_id=chat.id,
                        status='success'
                    )
                    db.add(history)
                    db.commit()
                except Exception as e:
                    logger.error(f"Ошибка записи истории: {e}")
                finally:
                    db.close()
                break
            else:
                last_error = error
                logger.debug(f"Не удалось отправить через {account.phone}: {error}")

        if not sent:
            fail_count += 1
            db = next(get_db())
            try:
                history = SentHistory(
                    account_id=None,
                    message_id=current_message.id,
                    chat_id=chat.id,
                    status='failed',
                    error_message=last_error
                )
                db.add(history)
                db.commit()
            except Exception as e:
                logger.error(f"Ошибка записи истории: {e}")
            finally:
                db.close()

        await asyncio.sleep(random.uniform(2, 4))

    db = next(get_db())
    try:
        from db.model import Queue
        queue_db = db.query(Queue).filter(Queue.id == queue.id).first()
        if queue_db:
            queue_db.last_sent_at = now
            queue_db.current_index = queue.current_index + 1
            if queue_db.current_index >= total_messages:
                queue_db.last_sent_date = now
            db.commit()
    except Exception as e:
        logger.error(f"Ошибка обновления очереди: {e}")
    finally:
        db.close()

    logger.info(f"Очередь {queue.id}: отправлено {success_count}/{len(chats)} чатов")


async def periodic_queue_broadcast():
    logger.info("🚀 Запуск фоновой задачи обработки очередей")
    while True:
        try:
            queues = get_active_queues()
            if queues:
                logger.info(f"Найдено активных очередей: {len(queues)}")
                for queue in queues:
                    await process_queue(queue)
            else:
                logger.debug("Нет активных очередей")
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("🛑 Задача обработки очередей остановлена")
            break
        except Exception as e:
            logger.exception(f"🔥 Ошибка в periodic_queue_broadcast: {e}")
            await asyncio.sleep(60)