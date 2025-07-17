import asyncio
import logging
import os
import re
from collections import defaultdict
import certifi

from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode, ContentType
from aiogram.types import (
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaDocument,
    InputMediaAudio,
    InputMediaAnimation,
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError  # Добавлен импорт
from dotenv import load_dotenv

# ========== ЗАГРУЗКА КОНФИГА ==========
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@midnight_project")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
FOOTER = (
    "\n\n"
    "<a href='https://t.me/Midnight_Project'>Midnight Project</a> | "
    "<a href='https://t.me/Midnight_Project/204'>Все проекты</a>"
)
ALBUM_TIMEOUT = float(os.getenv("ALBUM_TIMEOUT", 2.5))
# ============================

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ========== БУФЕР ДЛЯ АЛЬБОМОВ ==========
router = Router()
album_buffer = defaultdict(list)
album_tasks = {}

# ========== УТИЛИТЫ ==========
def extract_plain_text(html: str) -> str:
    text = re.sub(r'<[^>]*>', '', html or "")
    return text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')

async def send_log_to_admin(bot: Bot, text: str):
    try:
        await bot.send_message(
            ADMIN_ID,
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except TelegramAPIError as e:
        logger.error(f"Ошибка при отправке лога админу: {e}")

# ========== ФУНКЦИИ ПЕРЕПОСТА ==========
async def repost_single(bot: Bot, msg: types.Message):
    reply_id = msg.reply_to_message.message_id if msg.reply_to_message else None
    content = msg.html_text or (msg.caption or "")
    new_text = content + FOOTER

    if msg.content_type == ContentType.TEXT:
        new_msg = await bot.send_message(
            msg.chat.id,
            new_text,
            reply_to_message_id=reply_id,
            disable_web_page_preview=True,
        )
    elif msg.content_type == ContentType.PHOTO:
        new_msg = await bot.send_photo(
            msg.chat.id,
            msg.photo[-1].file_id,
            caption=new_text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=reply_id,
        )
    elif msg.content_type == ContentType.VIDEO:
        new_msg = await bot.send_video(
            msg.chat.id,
            msg.video.file_id,
            caption=new_text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=reply_id,
        )
    elif msg.content_type == ContentType.VOICE:
        new_msg = await bot.send_voice(
            msg.chat.id,
            msg.voice.file_id,
            caption=new_text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=reply_id,
        )
    elif msg.content_type == ContentType.DOCUMENT:
        new_msg = await bot.send_document(
            msg.chat.id,
            msg.document.file_id,
            caption=new_text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=reply_id,
        )
    elif msg.content_type == ContentType.AUDIO:
        new_msg = await bot.send_audio(
            msg.chat.id,
            msg.audio.file_id,
            caption=new_text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=reply_id,
        )
    elif msg.content_type == ContentType.ANIMATION:
        new_msg = await bot.send_animation(
            msg.chat.id,
            msg.animation.file_id,
            caption=new_text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=reply_id,
        )
    else:
        logger.info(f"Пропущен тип: {msg.content_type}")
        return

    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except TelegramAPIError as e:
        logger.error(f"Ошибка при удалении сообщения: {e}")

    emoji = {
        ContentType.TEXT: "✉️",
        ContentType.PHOTO: "📷",
        ContentType.VIDEO: "📹",
        ContentType.VOICE: "🎙️",
        ContentType.DOCUMENT: "📄",
        ContentType.AUDIO: "🎵",
        ContentType.ANIMATION: "🎞️",
    }.get(msg.content_type, "📌")
    
    log_text = (
        f"{emoji} <b>Перепост!</b>\n"
        f"<b>Тип:</b> {msg.content_type}\n"
        f"<b>Новый:</b> <a href='https://t.me/{msg.chat.username}/{new_msg.message_id}'>ссылка</a>\n"
        f"<b>Фрагмент:</b> {extract_plain_text(content)[:300]}"
    )
    await send_log_to_admin(bot, log_text)

async def repost_album(bot: Bot, messages: list[types.Message]):
    if not messages:
        return

    chat_id = messages[0].chat.id
    reply_id = messages[0].reply_to_message.message_id if messages[0].reply_to_message else None
    caption = (messages[0].caption or "") + FOOTER

    media = []
    for i, msg in enumerate(messages):
        params = {
            'media': None,
            'caption': caption if i == 0 else None,
            'parse_mode': ParseMode.HTML if i == 0 else None,
        }
        if msg.photo:
            params['media'] = msg.photo[-1].file_id
            media.append(InputMediaPhoto(**params))
        elif msg.video:
            params['media'] = msg.video.file_id
            media.append(InputMediaVideo(**params))
        elif msg.document:
            params['media'] = msg.document.file_id
            media.append(InputMediaDocument(**params))
        elif msg.audio:
            params['media'] = msg.audio.file_id
            media.append(InputMediaAudio(**params))
        elif msg.animation:
            params['media'] = msg.animation.file_id
            media.append(InputMediaAnimation(**params))

    try:
        new_msgs = await bot.send_media_group(
            chat_id=chat_id,
            media=media,
            reply_to_message_id=reply_id,
        )
    except TelegramAPIError as e:
        logger.error(f"Ошибка при отправке альбома: {e}")
        return

    for msg in messages:
        try:
            await bot.delete_message(chat_id, msg.message_id)
        except TelegramAPIError as e:
            logger.error(f"Ошибка при удалении сообщения: {e}")

    await send_log_to_admin(
        bot,
        f"🖼️ <b>Перепост альбома!</b>\n"
        f"<b>Медиа:</b> {len(new_msgs)} шт.\n"
        f"<b>Новый:</b> <a href='https://t.me/{messages[0].chat.username}/{new_msgs[0].message_id}'>ссылка</a>\n"
        f"<b>Фрагмент:</b> {extract_plain_text(caption)[:300]}"
    )

async def handle_album_timeout(bot: Bot, media_group_id: str, chat_id: int):
    await asyncio.sleep(ALBUM_TIMEOUT)
    key = (chat_id, media_group_id)
    msgs = album_buffer.pop(key, [])
    if key in album_tasks:
        del album_tasks[key]
    
    if not msgs:
        return
        
    try:
        if len(msgs) == 1:
            await repost_single(bot, msgs[0])
        else:
            await repost_album(bot, msgs)
    except TelegramAPIError as e:
        logger.error(f"Ошибка при обработке альбома: {e}")
        await send_log_to_admin(bot, f"❌ <b>Ошибка при перепосте:</b> <code>{e}</code>")

@router.channel_post()
async def handle_post(msg: types.Message, bot: Bot):
    if not msg.chat.username or msg.chat.username.lower() != CHANNEL_USERNAME.lstrip('@').lower():
        return
        
    if msg.media_group_id:
        key = (msg.chat.id, msg.media_group_id)
        album_buffer[key].append(msg)
        if key not in album_tasks:
            album_tasks[key] = asyncio.create_task(
                handle_album_timeout(bot, msg.media_group_id, msg.chat.id)
            )
    else:
        try:
            await repost_single(bot, msg)
        except TelegramAPIError as e:
            logger.error(f"Ошибка при обработке сообщения: {e}")

async def clear_console():
    while True:
        await asyncio.sleep(86400)
        os.system('cls' if os.name=='nt' else 'clear')

async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    asyncio.create_task(clear_console())
    
    try:
        await send_log_to_admin(bot, "🚀 Бот успешно запущен и готов к работе")
    except TelegramAPIError as e:
        logger.error(f"Ошибка при отправке стартового сообщения: {e}")

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())