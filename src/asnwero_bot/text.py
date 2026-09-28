from dataclasses import dataclass

from aiogram.types import Message


@dataclass(frozen=True)
class IncomingText:
    text: str
    is_forwarded: bool


def normalize_text(value: str, limit: int) -> str:
    lines = []
    for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        cleaned = " ".join(line.split())
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)[:limit].strip()


def extract_message_text(message: Message, limit: int) -> IncomingText | None:
    raw = message.text or message.caption
    if not raw:
        return None
    text = normalize_text(raw, limit)
    if not text:
        return None
    return IncomingText(text=text, is_forwarded=bool(message.forward_origin or message.forward_date))


def extract_reply_text(message: Message, limit: int) -> IncomingText | None:
    if not message.reply_to_message:
        return None
    return extract_message_text(message.reply_to_message, limit)


def preview(text: str, limit: int = 280) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}..."
