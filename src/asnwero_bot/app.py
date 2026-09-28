from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats

from asnwero_bot.config import get_settings
from asnwero_bot.handlers import build_router
from asnwero_bot.models import GeminiProvider, GroqProvider, OpenRouterProvider, ProviderRouter, XAIProvider
from asnwero_bot.storage import Storage


async def setup_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начать работу"),
            BotCommand(command="help", description="Как пользоваться ботом"),
            BotCommand(command="privacy", description="Приватность и хранение данных"),
            BotCommand(command="cancel", description="Сбросить текущий сценарий"),
        ],
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.set_my_commands(
        [BotCommand(command="answer", description="Подсказать ответ на выбранное сообщение")],
        scope=BotCommandScopeAllGroupChats(),
    )


async def run() -> None:
    settings = get_settings()
    settings.validate_runtime()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    storage = Storage(settings.database_path, ttl_hours=settings.task_ttl_hours)
    await storage.init()

    providers = [
        GeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.request_timeout_seconds),
        GroqProvider(settings.groq_api_key, settings.groq_model, settings.request_timeout_seconds),
        OpenRouterProvider(
            settings.openrouter_api_key,
            settings.openrouter_model,
            settings.request_timeout_seconds,
            settings.allow_paid_models,
            settings.openrouter_site_url,
            settings.openrouter_app_name,
        ),
    ]
    if settings.xai_enabled:
        providers.append(
            XAIProvider(
                settings.xai_api_key,
                settings.xai_model,
                settings.request_timeout_seconds,
                settings.allow_paid_models,
            )
        )
    model_router = ProviderRouter(providers)

    bot = Bot(settings.telegram_bot_token)
    await setup_bot_commands(bot)
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(storage, model_router, settings))
    await dispatcher.start_polling(bot)
