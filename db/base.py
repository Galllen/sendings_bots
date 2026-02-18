import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from bot import logger
from db.model import Base, Message, Chat, MessageChatMapping, Account, User, Tag
from dotenv import load_dotenv

load_dotenv()
ADMIN_TELEGRAM_ID = int(os.getenv('acc_admin', '0'))

engine = create_engine('sqlite:///data.db')
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_account_session_valid(session_file: str) -> bool:
    return (
            os.path.exists(session_file)
            and os.path.getsize(session_file) > 100
    )


def get_messages_paginated(offset: int, limit: int):
    db = next(get_db())
    try:
        messages = db.query(Message).order_by(Message.id).offset(offset).limit(limit).all()
        total = db.query(Message).count()
        return messages, total
    finally:
        db.close()


def get_message_by_id(msg_id: int):
    db = next(get_db())
    try:
        msg = db.query(Message).filter(Message.id == msg_id).first()
        return msg
    finally:
        db.close()


def get_chats_by_message_id(msg_id: int):
    db = next(get_db())
    try:
        mappings = db.query(MessageChatMapping).filter(MessageChatMapping.message_id == msg_id).all()
        chats = []
        for m in mappings:
            chat = db.query(Chat).filter(Chat.id == m.chat_id).first()
            if chat:
                chats.append(chat)
        return chats
    finally:
        db.close()



def toggle_message_status(msg_id: int):
    db = next(get_db())
    try:
        msg = db.query(Message).filter(Message.id == msg_id).first()
        if msg:
            msg.is_enabled = not msg.is_enabled
            db.commit()
            return msg.is_enabled
    finally:
        db.close()


def get_accounts_paginated(offset: int, limit: int):
    db = next(get_db())
    try:
        accounts = (
            db.query(Account)
            .order_by(Account.is_active.desc(), Account.id)
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = db.query(Account).count()
        return accounts, total
    finally:
        db.close()


def get_account_by_id(acc_id: int):
    db = next(get_db())
    try:
        acc = db.query(Account).filter(Account.id == acc_id).first()
        return acc
    finally:
        db.close()


def toggle_account_status(acc_id: int):
    db = next(get_db())
    try:
        acc = db.query(Account).filter(Account.id == acc_id).first()
        if acc:
            acc.is_active = not acc.is_active
            db.commit()
            return acc.is_active
    finally:
        db.close()


def get_chats_paginated(offset: int, limit: int):
    db = next(get_db())
    try:
        chats = (
            db.query(Chat)
            .order_by(Chat.is_enabled.desc(), Chat.id)
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = db.query(Chat).count()
        return chats, total
    finally:
        db.close()


def get_chat_by_id(chat_id: int):
    db = next(get_db())
    try:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        return chat
    finally:
        db.close()


def toggle_chat_status(chat_id: int):
    db = next(get_db())
    try:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if chat:
            chat.is_enabled = not chat.is_enabled
            db.commit()
            return chat.is_enabled
    finally:
        db.close()


def get_user_role(user_id: int):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if user:
            return user.role
        return "user"
    except Exception as e:
        logger.error(f"Error fetching user role for {user_id}: {e}")
        return "user"
    finally:
        db.close()


def set_user_role(user_id: int, username: str, role: str = "user"):
    db = next(get_db())
    try:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if user:
            user.role = role
        else:
            new_user = User(telegram_id=user_id, username=username, role=role)
            db.add(new_user)
            db.commit()
    except Exception as e:
        logger.error(f"Error setting user role for {user_id}: {e}")
    finally:
        db.close()


def save_message(name: str, content: str, interval_hours: float):
    db = next(get_db())
    try:
        new_msg = Message(name=name, content=content, interval_hours=float(interval_hours))
        db.add(new_msg)
        db.commit()
        db.refresh(new_msg)
        return new_msg.id
    finally:
        db.close()


def save_account(phone, session_file, api_id=None, api_hash=None, is_active=True):
    db = next(get_db())
    try:
        admin_telegram_id = ADMIN_TELEGRAM_ID
        user = db.query(User).filter(User.telegram_id == admin_telegram_id).first()
        if not user:
            user = User(
                telegram_id=admin_telegram_id,
                username=f"admin_{admin_telegram_id}",
                role="admin"
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        existing_account = db.query(Account).filter(Account.phone == phone).first()
        if existing_account:
            existing_account.session_file = session_file
            existing_account.api_id = api_id
            existing_account.api_hash = api_hash
            existing_account.is_active = is_active
            db.commit()
            db.refresh(existing_account)
            return existing_account.id
        else:
            account = Account(
                user_id=user.id,
                phone=phone,
                session_file=session_file,
                api_id=api_id,
                api_hash=api_hash,
                is_active=is_active
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            return account.id
    finally:
        db.close()


def save_chat(chat_id: str, title: str):
    db = next(get_db())
    try:
        new_chat = Chat(chat_id=chat_id, title=title)
        db.add(new_chat)
        db.commit()
        db.refresh(new_chat)
        return new_chat.id
    finally:
        db.close()


def get_active_accounts():
    db = next(get_db())
    try:
        accounts = db.query(Account).filter(Account.is_active == True).all()
        valid_accounts = [
            acc for acc in accounts
            if is_account_session_valid(acc.session_file)
        ]
        return valid_accounts
    finally:
        db.close()


def del_message_by_id(message_id: int) -> bool:
    db = next(get_db())
    try:
        message = db.query(Message).filter(Message.id == message_id).first()
        if not message:
            return False
        db.query(MessageChatMapping).filter(
            MessageChatMapping.message_id == message_id
        ).delete(synchronize_session=False)

        db.query(Message).filter(Message.id == message_id).delete()

        db.commit()
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка удаления сообщения {message_id}: {e}")
        return False

    finally:
        db.close()

def link_message_to_chats(message_id: int, chat_ids: list[int]):
    db = next(get_db())
    try:
        db.query(MessageChatMapping).filter(MessageChatMapping.message_id == message_id).delete()
        for chat_id in chat_ids:
            mapping = MessageChatMapping(message_id=message_id, chat_id=chat_id)
            db.add(mapping)

        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка привязки чатов к сообщению {message_id}: {e}")
        return False
    finally:
        db.close()


def get_unlinked_chats_for_message(message_id: int):
    db = next(get_db())
    try:
        all_chats = db.query(Chat).filter(Chat.is_enabled == True).all()
        linked_chat_ids = db.query(MessageChatMapping.chat_id) \
            .filter(MessageChatMapping.message_id == message_id) \
            .all()
        linked_ids = [c[0] for c in linked_chat_ids]


        unlinked = [c for c in all_chats if c.id not in linked_ids]
        return unlinked
    finally:
        db.close()


def get_linked_chats_for_message(message_id: int):
    db = next(get_db())
    try:
        mappings = db.query(MessageChatMapping).filter(MessageChatMapping.message_id == message_id).all()
        chats = []
        for m in mappings:
            chat = db.query(Chat).filter(Chat.id == m.chat_id).first()
            if chat:
                chats.append(chat)
        return chats
    finally:
        db.close()