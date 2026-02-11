from sqlalchemy import Column, Integer, Text, Boolean, DateTime, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Tag(Base):
    __tablename__ = 'tags'
    id = Column(Integer, primary_key=True)
    name = Column(Text, unique=True, nullable=False)
    description = Column(Text)

class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    interval_hours = Column(Integer, default=24)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    tag_id = Column(Integer, ForeignKey('tags.id'))


    tag = relationship('Tag')

class Chat(Base):
    __tablename__ = 'chats'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Text, nullable=False)
    title = Column(Text)
    is_enabled = Column(Boolean, default=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    tag_id = Column(Integer, ForeignKey('tags.id'))


    tag = relationship('Tag')

class MessageChatMapping(Base):
    __tablename__ = 'message_chat_mapping'
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey('messages.id'), nullable=False)
    chat_id = Column(Integer, ForeignKey('chats.id'), nullable=False)

    __table_args__ = (UniqueConstraint('message_id', 'chat_id'),)

    message = relationship('Message', backref='mapped_chats')
    chat = relationship('Chat', backref='mapped_messages')


class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    phone = Column(Text, unique=True, nullable=False)
    session_file = Column(Text, nullable=False)
    api_id = Column(Integer)
    api_hash = Column(Text)
    proxy = Column(Text)
    is_active = Column(Boolean, default=1)
    added_at = Column(DateTime, default=datetime.utcnow)
    tag_id = Column(Integer, ForeignKey('tags.id'))

    tag = relationship('Tag')

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(Text)
    role = Column(Text, default='user')

