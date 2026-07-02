from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat_context import build_account_context
from app.database import get_db
from app.deps import get_active_account
from app.errors import ApiError
from app.gemini_client import generate_reply
from app.ids import new_id
from app.models import Account, ChatMessage, Conversation, SuggestionChip
from app.timeutil import to_iso_kst, utcnow

router = APIRouter(prefix="/chat", tags=["chat"])

TITLE_PREVIEW_LENGTH = 22


class ChatMessageOut(BaseModel):
    id: str
    role: str
    text: str
    createdAt: str


class ConversationSummaryOut(BaseModel):
    id: str
    title: str
    lastMessagePreview: Optional[str] = None
    messageCount: int
    createdAt: str
    updatedAt: str


class ConversationOut(BaseModel):
    id: str
    title: str
    messages: list[ChatMessageOut]
    createdAt: str
    updatedAt: str


class ConversationBriefOut(BaseModel):
    id: str
    title: str
    updatedAt: str


class MessageAppendOut(BaseModel):
    conversationId: str
    appendedMessages: list[ChatMessageOut]
    conversation: ConversationBriefOut


class CreateConversationIn(BaseModel):
    title: Optional[str] = None
    initialMessage: Optional[str] = None


class RenameConversationIn(BaseModel):
    title: str


class SendMessageIn(BaseModel):
    text: str


class SuggestionChipOut(BaseModel):
    id: str
    icon: Optional[str] = None
    label: str
    prompt: str


class ChatSuggestionsOut(BaseModel):
    insightSuggestions: list[SuggestionChipOut]
    suggestionPool: list[SuggestionChipOut]


class InsightQueryIn(BaseModel):
    text: str


class InsightQueryOut(BaseModel):
    reply: str


def _message_out(message: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=message.id, role=message.role, text=message.text, createdAt=to_iso_kst(message.created_at)
    )


def _title_from_text(text: str) -> str:
    if len(text) <= TITLE_PREVIEW_LENGTH:
        return text
    return f"{text[:TITLE_PREVIEW_LENGTH]}…"


def _require_text(text: Optional[str]) -> str:
    trimmed = (text or "").strip()
    if not trimmed:
        raise ApiError(400, "INVALID_MESSAGE", "메시지를 입력해주세요.", field="text")
    if len(trimmed) > 2000:
        raise ApiError(400, "MESSAGE_TOO_LONG", "메시지는 2000자 이하로 입력해주세요.", field="text")
    return trimmed


def _get_owned_conversation(db: Session, account_id: str, conversation_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.account_id != account_id:
        raise ApiError(404, "NOT_FOUND", "대화를 찾을 수 없습니다.")
    return conversation


def _list_messages(db: Session, conversation_id: str) -> list[ChatMessage]:
    return list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at)
        ).all()
    )


def _to_summary(db: Session, conversation: Conversation) -> ConversationSummaryOut:
    messages = _list_messages(db, conversation.id)
    last_message = messages[-1] if messages else None
    return ConversationSummaryOut(
        id=conversation.id,
        title=conversation.title,
        lastMessagePreview=last_message.text if last_message else None,
        messageCount=len(messages),
        createdAt=to_iso_kst(conversation.created_at),
        updatedAt=to_iso_kst(conversation.updated_at),
    )


@router.get("/conversations", response_model=list[ConversationSummaryOut])
def list_conversations(
    account: Account = Depends(get_active_account),
    db: Session = Depends(get_db),
) -> list[ConversationSummaryOut]:
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.account_id == account.id)
        .order_by(Conversation.updated_at.desc())
    ).all()
    return [_to_summary(db, c) for c in conversations]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: str,
    account: Account = Depends(get_active_account),
    db: Session = Depends(get_db),
) -> ConversationOut:
    conversation = _get_owned_conversation(db, account.id, conversation_id)
    messages = _list_messages(db, conversation.id)
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        messages=[_message_out(m) for m in messages],
        createdAt=to_iso_kst(conversation.created_at),
        updatedAt=to_iso_kst(conversation.updated_at),
    )


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(
    body: CreateConversationIn,
    account: Account = Depends(get_active_account),
    db: Session = Depends(get_db),
) -> ConversationOut:
    title_in = (body.title or "").strip()
    initial_message = (body.initialMessage or "").strip()
    if not title_in and not initial_message:
        raise ApiError(400, "INVALID_TITLE", "대화 제목 또는 첫 메시지를 입력해주세요.", field="title")
    if initial_message and len(initial_message) > 2000:
        raise ApiError(400, "MESSAGE_TOO_LONG", "메시지는 2000자 이하로 입력해주세요.", field="text")

    created_at = utcnow()
    title = title_in or _title_from_text(initial_message)
    conversation = Conversation(
        id=new_id("chat"),
        account_id=account.id,
        title=title,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(conversation)
    db.flush()

    messages: list[ChatMessage] = []
    if initial_message:
        user_message = ChatMessage(
            id=new_id("msg"),
            conversation_id=conversation.id,
            role="user",
            text=initial_message,
            created_at=created_at,
        )
        db.add(user_message)
        messages.append(user_message)

        try:
            context = build_account_context(db, account.id)
            reply_text = generate_reply(context, initial_message)
        except ApiError:
            db.rollback()
            raise

        assistant_created_at = utcnow()
        assistant_message = ChatMessage(
            id=new_id("msg"),
            conversation_id=conversation.id,
            role="assistant",
            text=reply_text,
            created_at=assistant_created_at,
        )
        db.add(assistant_message)
        messages.append(assistant_message)
        conversation.updated_at = assistant_created_at

    db.commit()
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        messages=[_message_out(m) for m in messages],
        createdAt=to_iso_kst(conversation.created_at),
        updatedAt=to_iso_kst(conversation.updated_at),
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummaryOut)
def rename_conversation(
    conversation_id: str,
    body: RenameConversationIn,
    account: Account = Depends(get_active_account),
    db: Session = Depends(get_db),
) -> ConversationSummaryOut:
    title = (body.title or "").strip()
    if not title:
        raise ApiError(400, "INVALID_TITLE", "대화 제목을 입력해주세요.", field="title")

    conversation = _get_owned_conversation(db, account.id, conversation_id)
    conversation.title = title
    db.commit()
    return _to_summary(db, conversation)


@router.delete("/conversations/{conversation_id}", status_code=204, response_model=None)
def delete_conversation(
    conversation_id: str,
    account: Account = Depends(get_active_account),
    db: Session = Depends(get_db),
) -> None:
    conversation = _get_owned_conversation(db, account.id, conversation_id)
    db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation.id).delete()
    db.delete(conversation)
    db.commit()
    return None


@router.post("/conversations/{conversation_id}/messages", response_model=MessageAppendOut)
def send_message(
    conversation_id: str,
    body: SendMessageIn,
    account: Account = Depends(get_active_account),
    db: Session = Depends(get_db),
) -> MessageAppendOut:
    text = _require_text(body.text)
    conversation = _get_owned_conversation(db, account.id, conversation_id)

    prior_messages = _list_messages(db, conversation.id)
    history = [(m.role, m.text) for m in prior_messages]

    created_at = utcnow()
    user_message = ChatMessage(
        id=new_id("msg"),
        conversation_id=conversation.id,
        role="user",
        text=text,
        created_at=created_at,
    )
    db.add(user_message)

    try:
        context = build_account_context(db, account.id)
        reply_text = generate_reply(context, text, history=history)
    except ApiError:
        db.rollback()
        raise

    assistant_created_at = utcnow()
    assistant_message = ChatMessage(
        id=new_id("msg"),
        conversation_id=conversation.id,
        role="assistant",
        text=reply_text,
        created_at=assistant_created_at,
    )
    db.add(assistant_message)
    conversation.updated_at = assistant_created_at
    db.commit()

    return MessageAppendOut(
        conversationId=conversation.id,
        appendedMessages=[_message_out(user_message), _message_out(assistant_message)],
        conversation=ConversationBriefOut(
            id=conversation.id, title=conversation.title, updatedAt=to_iso_kst(conversation.updated_at)
        ),
    )


@router.get("/suggestions", response_model=ChatSuggestionsOut)
def get_suggestions(db: Session = Depends(get_db)) -> ChatSuggestionsOut:
    insight_chips = db.scalars(
        select(SuggestionChip)
        .where(SuggestionChip.group == "insight_suggestion")
        .order_by(SuggestionChip.seq)
    ).all()
    pool_chips = db.scalars(
        select(SuggestionChip).where(SuggestionChip.group == "suggestion_pool").order_by(SuggestionChip.seq)
    ).all()

    def to_out(chip: SuggestionChip) -> SuggestionChipOut:
        return SuggestionChipOut(id=chip.id, icon=chip.icon, label=chip.label, prompt=chip.prompt)

    return ChatSuggestionsOut(
        insightSuggestions=[to_out(c) for c in insight_chips],
        suggestionPool=[to_out(c) for c in pool_chips],
    )


@router.post("/insight-queries", response_model=InsightQueryOut)
def ask_insight(
    body: InsightQueryIn,
    account: Account = Depends(get_active_account),
    db: Session = Depends(get_db),
) -> InsightQueryOut:
    text = _require_text(body.text)
    context = build_account_context(db, account.id)
    reply = generate_reply(context, text)
    return InsightQueryOut(reply=reply)
