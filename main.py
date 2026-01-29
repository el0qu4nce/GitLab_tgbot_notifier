import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from config import TELEGRAM_BOT_TOKEN, USER_CONFIG, get_user_config, get_all_chat_ids
from parser import (init_gitlab_client, get_last_pipeline, format_pipeline_message, get_second_last_mr_details,
                    test_gitlab_connection)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def init_all_gitlab_clients():
    initialized = 0
    failed = 0

    for chat_id in get_all_chat_ids():
        user_config = get_user_config(chat_id)
        if user_config:
            gitlab_token = user_config.get('gitlab_token')
            if gitlab_token and gitlab_token != 'ВАШ_GITLAB_TOKEN_ЗДЕСЬ':
                client = init_gitlab_client(chat_id, gitlab_token)
                if client:
                    initialized += 1
                else:
                    failed += 1
                    logger.error(f"Не удалось инициализировать GitLab для chat_id: {chat_id}")

    return initialized, failed


def log_chat_info(update: Update, command: str = None):
    user = update.effective_user
    chat_id = update.effective_chat.id

    timestamp = datetime.now().strftime('%H:%M:%S')

    username = user.username or "no_username"
    first_name = user.first_name or ""

    if command:
        print(f"{timestamp} - {username} - {first_name} - {chat_id} - {command}")
    else:
        print(f"{timestamp} - {username} - {first_name} - {chat_id}")


async def log_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_chat_info(update)


async def pipeline_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_chat_info(update, "/pipeline")

    chat_id = update.effective_chat.id

    user_config = get_user_config(chat_id)
    if not user_config:
        await update.message.reply_text("❌ Chat not configured")
        return

    gitlab_token = user_config.get('gitlab_token')
    project_id = user_config.get('project_id')

    if not gitlab_token or gitlab_token == 'ВАШ_GITLAB_TOKEN_ЗДЕСЬ':
        await update.message.reply_text("❌ GitLab token not configured")
        return

    if not project_id:
        await update.message.reply_text("❌ Project ID not configured")
        return

    from parser import get_gitlab_client
    if not get_gitlab_client(chat_id):
        client = init_gitlab_client(chat_id, gitlab_token)
        if not client:
            await update.message.reply_text("❌ Failed to initialize GitLab client")
            return

    try:
        pipeline_info = get_last_pipeline(chat_id, project_id)

        if pipeline_info:
            message = format_pipeline_message(pipeline_info)

            await update.message.reply_text(
                message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
        else:
            await update.message.reply_text("❌ No pipeline found")

    except Exception as e:
        logger.error(f"Error in pipeline_command for chat_id {chat_id}: {e}")
        await update.message.reply_text(
            f"❌ Error: {str(e)[:200]}"
        )


async def mr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_chat_info(update, "/mr")

    chat_id = update.effective_chat.id

    user_config = get_user_config(chat_id)
    if not user_config:
        await update.message.reply_text("❌ Chat not configured")
        return

    gitlab_token = user_config.get('gitlab_token')
    project_id = user_config.get('project_id')

    if not gitlab_token or gitlab_token == 'ВАШ_GITLAB_TOKEN_ЗДЕСЬ':
        await update.message.reply_text("❌ GitLab token not configured")
        return

    if not project_id:
        await update.message.reply_text("❌ Project ID not configured")
        return

    from parser import get_gitlab_client
    if not get_gitlab_client(chat_id):
        client = init_gitlab_client(chat_id, gitlab_token)
        if not client:
            await update.message.reply_text("❌ Failed to initialize GitLab client")
            return

    try:
        mr_info = get_second_last_mr_details(chat_id, project_id)

        await update.message.reply_text(
            mr_info,
            parse_mode='Markdown',
            disable_web_page_preview=False
        )

    except Exception as e:
        logger.error(f"Error in mr_command for chat_id {chat_id}: {e}")
        await update.message.reply_text(
            f"❌ Error: {str(e)[:200]}"
        )


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_chat_info(update, "/chatid")

    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Chat ID: `{chat_id}`", parse_mode='Markdown')


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_chat_info(update, "/status")

    chat_id = update.effective_chat.id

    user_config = get_user_config(chat_id)
    if user_config:
        gitlab_token = user_config.get('gitlab_token', '')
        project_id = user_config.get('project_id', '')

        from parser import get_gitlab_client
        gitlab_client = get_gitlab_client(chat_id)

        status_msg = (
            f"✅ Chat configured\n"
            f"Project ID: {project_id}\n"
            f"GitLab client: {'✅ Initialized' if gitlab_client else '❌ Not initialized'}"
        )

        if gitlab_token and gitlab_token != 'ВАШ_GITLAB_TOKEN_ЗДЕСЬ' and not gitlab_client:
            success, message = test_gitlab_connection(chat_id, gitlab_token)
            status_msg += f"\n\nConnection test: {message}"
    else:
        status_msg = "❌ Chat not configured"

    await update.message.reply_text(status_msg)


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_chat_info(update, "/test")

    chat_id = update.effective_chat.id

    user_config = get_user_config(chat_id)
    if not user_config:
        await update.message.reply_text("❌ Chat not configured")
        return

    gitlab_token = user_config.get('gitlab_token')
    if not gitlab_token or gitlab_token == 'ВАШ_GITLAB_TOKEN_ЗДЕСЬ':
        await update.message.reply_text("❌ GitLab token not configured")
        return

    await update.message.reply_text("🔄 Testing GitLab connection...")

    success, message = test_gitlab_connection(chat_id, gitlab_token)
    await update.message.reply_text(message)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_chat_info(update, "UNKNOWN_CMD")
    await update.message.reply_text("❌ Unknown command. Use /help for available commands.")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

    if update and update.message:
        if update.effective_user:
            user = update.effective_user
            timestamp = datetime.now().strftime('%H:%M:%S')
            username = user.username or "no_username"
            first_name = user.first_name or ""
            chat_id = update.effective_chat.id
            print(f"{timestamp} - {username} - {first_name} - {chat_id} - ERROR: {context.error}")

        await update.message.reply_text("❌ Error occurred")


def main():
    if TELEGRAM_BOT_TOKEN == "ВАШ_TELEGRAM_BOT_TOKEN_ЗДЕСЬ":
        print("=" * 50)
        print("❌ ОШИБКА: Токен Telegram бота не установлен!")
        print("   Замените 'ВАШ_TELEGRAM_BOT_TOKEN_ЗДЕСЬ' в config.py")
        print("   на ваш реальный токен от @BotFather")
        print("=" * 50)
        return

    print("🔄 Инициализация GitLab клиентов...")
    initialized, failed = init_all_gitlab_clients()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("pipeline", pipeline_command))
    application.add_handler(CommandHandler("mr", mr_command))
    application.add_handler(CommandHandler("chatid", chatid_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("test", test_command))

    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    application.add_handler(MessageHandler(filters.ALL, log_all_messages))
    application.add_error_handler(error_handler)

    # Запускаем бота
    print("=" * 50)
    print("🤖 Technical GitLab Bot Started")
    print("=" * 50)
    print(f"Configured chats: {len(USER_CONFIG)}")
    print(f"GitLab clients: ✅ {initialized} initialized, ❌ {failed} failed")
    print("\nLog format: [time - username - first_name - chat_id]")
    print("\nAvailable commands:")
    print("  /pipeline - последний pipeline")
    print("  /mr - предпоследний merge request")
    print("  /chatid - показать chat id")
    print("  /status - статус конфигурации")
    print("  /test - тест подключения к GitLab")
    print("\n⚠️  Все сообщения логируются в терминал")
    print("=" * 50)

    application.run_polling()


if __name__ == '__main__':
    main()
