from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from asnwero_bot.config import Settings
from asnwero_bot.keyboards import intake_keyboard, result_keyboard, tone_keyboard
from asnwero_bot.models import ProviderRouter, TemporaryProviderError
from asnwero_bot.prompts import TONE_LABELS
from asnwero_bot.storage import Storage
from asnwero_bot.text import extract_message_text, extract_reply_text, normalize_text, preview

logger = logging.getLogger(__name__)


async def answer_callback(query: CallbackQuery) -> None:
    try:
        await query.answer()
    except TelegramBadRequest as exc:
        if "query is too old" not in str(exc):
            raise


def build_router(storage: Storage, model_router: ProviderRouter, settings: Settings) -> Router:
    router = Router()

    @router.message(Command("start", "help"))
    async def start(message: Message) -> None:
        await message.answer(
            "Привет. Пришли мне текст или перешли сообщение, на которое нужен ответ. "
            "Я покажу тоны и верну три варианта, а ты сам отправишь подходящий."
        )

    @router.message(Command("privacy"))
    async def privacy(message: Message) -> None:
        await message.answer(
            "Я храню только текущий текст, опциональный контекст и состояние выбора до 24 часов. "
            "Для генерации текущий текст отправляется выбранному AI-провайдеру. "
            "Ключи и полный текст переписки в логи не пишутся."
        )

    @router.message(Command("cancel"))
    async def cancel(message: Message) -> None:
        await storage.clear_task(message.from_user.id)
        await message.answer("Сбросил текущий сценарий. Пришли новое сообщение.")

    @router.message(Command("answer"))
    async def answer_command(message: Message) -> None:
        if message.chat.type == "private":
            await message.answer("Пришли или перешли сюда сообщение, на которое нужен ответ.")
            return
        if not message.from_user:
            return
        incoming = extract_reply_text(message, settings.max_source_chars)
        if not incoming:
            await message.reply("Напиши /answer ответом на текстовое сообщение, для которого нужен ответ.")
            return
        await storage.save_task(message.from_user.id, incoming.text, stage="tone")
        try:
            await message.bot.send_message(
                message.from_user.id,
                f"Взял сообщение из группы:\n\n{preview(incoming.text)}\n\nКак ответить?",
                reply_markup=intake_keyboard(),
            )
        except (TelegramBadRequest, TelegramForbiddenError):
            bot_user = await message.bot.get_me()
            await message.reply(
                f"Сначала открой личный чат с ботом и нажми /start: https://t.me/{bot_user.username}\n"
                "Потом снова напиши /answer ответом на нужное сообщение."
            )
            return
        await message.reply("Отправил варианты действий тебе в личку.")

    @router.callback_query(lambda query: query.data and query.data.startswith("tone:"))
    async def choose_tone(query: CallbackQuery) -> None:
        await answer_callback(query)
        user_id = query.from_user.id
        task = await storage.get_task(user_id)
        if not task:
            await query.message.answer("Я не вижу исходного сообщения. Пришли текст заново.")
            return
        tone = query.data.split(":", 1)[1]
        if tone == "custom":
            await storage.update_task(user_id, stage="custom_tone")
            await query.message.answer("Напиши пожелание к тону. Например: «вежливо откажи» или «ответь как другу».")
            return
        await storage.update_task(user_id, tone=tone, stage="ready")
        await generate_and_send(query.message, user_id, tone, task.context)

    @router.callback_query(lambda query: query.data and query.data.startswith("action:"))
    async def result_action(query: CallbackQuery) -> None:
        await answer_callback(query)
        user_id = query.from_user.id
        action = query.data.split(":", 1)[1]
        task = await storage.get_task(user_id)
        if action == "new":
            await storage.clear_task(user_id)
            await query.message.answer("Ок, пришли новое сообщение.")
            return
        if not task:
            await query.message.answer("Текущий сценарий уже сброшен. Пришли сообщение заново.")
            return
        if action == "choose_tone":
            await storage.update_task(user_id, stage="tone")
            await query.message.answer(f"Исходное сообщение:\n\n{preview(task.source_text)}\n\nКак ответить?", reply_markup=tone_keyboard())
            return
        if action == "add_context":
            await storage.update_task(user_id, stage="await_context")
            await query.message.answer("Напиши короткий контекст. Например: «это друг, спорим о поездке, я не хочу ехать».")
            return
        if action == "other_tone":
            await storage.update_task(user_id, stage="tone")
            await query.message.answer(f"Исходное сообщение:\n\n{preview(task.source_text)}\n\nКак ответить?", reply_markup=tone_keyboard())
            return
        if action == "more":
            if not task.tone:
                await query.message.answer("Сначала выбери тон.", reply_markup=tone_keyboard())
                return
            await generate_and_send(query.message, user_id, task.tone, task.context)

    @router.message()
    async def any_message(message: Message) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        if message.chat.type != "private":
            return
        task = await storage.get_task(user_id)
        if task and task.stage == "await_context":
            context = normalize_text(message.text or message.caption or "", settings.max_context_chars)
            if not context:
                await message.answer("Контекст нужен текстом. Или нажми «Выбрать тон» и продолжим без него.", reply_markup=intake_keyboard())
                return
            await storage.update_task(user_id, stage="tone", context=context)
            await message.answer("Принял контекст. Теперь выбери тон.", reply_markup=tone_keyboard())
            return
        if task and task.stage == "custom_tone":
            custom_tone = normalize_text(message.text or message.caption or "", 120)
            if not custom_tone:
                await message.answer("Напиши пожелание текстом.")
                return
            await storage.update_task(user_id, stage="ready", tone=custom_tone)
            await generate_and_send(message, user_id, custom_tone, task.context)
            return
        incoming = extract_message_text(message, settings.max_source_chars)
        if not incoming:
            await message.answer("Пока умею работать только с текстом. Скопируй или перешли текстовое сообщение.")
            return
        await storage.save_task(user_id, incoming.text, stage="tone")
        await message.answer(
            f"Вижу текст переписки:\n\n{preview(incoming.text)}\n\nКак ответить?",
            reply_markup=intake_keyboard(),
        )

    async def generate_and_send(message: Message, user_id: int, tone: str, context: str | None) -> None:
        task = await storage.get_task(user_id)
        if not task:
            await message.answer("Я не вижу исходного сообщения. Пришли текст заново.")
            return
        recent = await storage.count_recent_generations(user_id)
        if recent >= settings.rate_limit_per_hour:
            await message.answer("Лимит генераций на час исчерпан. Попробуй чуть позже.")
            return
        await message.answer("Генерирую три варианта...")
        try:
            variants = await model_router.generate(task.source_text, tone, context)
        except TemporaryProviderError:
            await message.answer("Сейчас бесплатные модели недоступны. Попробуй позже.", reply_markup=result_keyboard())
            return
        await storage.record_generation(user_id)
        await storage.update_task(user_id, stage="ready", tone=tone)
        tone_title = TONE_LABELS.get(tone, tone)
        text = "\n\n".join(f"{index}. {variant}" for index, variant in enumerate(variants, start=1))
        await message.answer(f"{tone_title}\n\n{text}", reply_markup=result_keyboard())

    return router
