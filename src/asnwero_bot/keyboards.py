from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from asnwero_bot.prompts import TONE_LABELS


def tone_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"🧱 {TONE_LABELS['firm']}", callback_data="tone:firm"), InlineKeyboardButton(text=f"😄 {TONE_LABELS['funny']}", callback_data="tone:funny")],
        [InlineKeyboardButton(text=f"🤝 {TONE_LABELS['constructive']}", callback_data="tone:constructive"), InlineKeyboardButton(text=f"🔬 {TONE_LABELS['scientific']}", callback_data="tone:scientific")],
        [InlineKeyboardButton(text=f"🎯 {TONE_LABELS['short']}", callback_data="tone:short")],
        [InlineKeyboardButton(text="✍️ Свой вариант", callback_data="tone:custom")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def intake_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎛️ Выбрать тон", callback_data="action:choose_tone")],
            [InlineKeyboardButton(text="🧩 Добавить контекст", callback_data="action:add_context")],
            [InlineKeyboardButton(text="🆕 Новое сообщение", callback_data="action:new")],
        ]
    )


def result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎛️ Другой тон", callback_data="action:other_tone"), InlineKeyboardButton(text="🔁 Еще варианты", callback_data="action:more")],
            [InlineKeyboardButton(text="🆕 Новое сообщение", callback_data="action:new")],
        ]
    )
