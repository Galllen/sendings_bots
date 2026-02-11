from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker

from bot import logger
from db.model import Base, Message, Chat, MessageChatMapping, Account, User

engine = create_engine('sqlite:///data.db')
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
            .order_by(Account.is_active.desc(), Account.id)  # активные первыми
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

#add

def save_message(name: str, content: str, interval_hours: int):
    db = next(get_db())
    try:
        new_msg = Message(name=name, content=content, interval_hours=interval_hours)
        db.add(new_msg)
        db.commit()
        db.refresh(new_msg)
        return new_msg.id
    finally:
        db.close()


def save_account(phone: str, session_file: str):
    db = next(get_db())
    try:
        new_acc = Account(phone=phone, session_file=session_file)
        db.add(new_acc)
        db.commit()
        db.refresh(new_acc)
        return new_acc.id
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