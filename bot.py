import logging
import subprocess
import psutil
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# Замените на токен вашего бота
TOKEN = "8137824543:AAGKP32Rjj_ctA5horpEVoKOezJSBNhsRfg"
# Укажите MAC-адрес для отправки WOL (если требуется)
WOL_MAC = "b0:6e:bf:c8:3e:ba"  # замените на нужный MAC

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Главное меню
def main_menu():
    keyboard = [
        [InlineKeyboardButton("Управление аудио", callback_data='menu_audio')],
        [InlineKeyboardButton("Управление питанием", callback_data='menu_power')],
        [InlineKeyboardButton("Управление приложениями", callback_data='menu_apps')],
        [InlineKeyboardButton("Мониторинг системы", callback_data='menu_monitor')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Меню управления аудио
def audio_menu():
    keyboard = [
        [InlineKeyboardButton("Пауза/Воспроизведение", callback_data='audio_playpause')],
        [InlineKeyboardButton("Следующий трек", callback_data='audio_next')],
        [InlineKeyboardButton("Предыдущий трек", callback_data='audio_prev')],
        [InlineKeyboardButton("Управление громкостью", callback_data='audio_volume')],
        [InlineKeyboardButton("Назад", callback_data='back_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Подменю управления громкостью
def volume_menu():
    keyboard = [
        [InlineKeyboardButton("25%", callback_data='audio_volume_25'), InlineKeyboardButton("50%", callback_data='audio_volume_50')],
        [InlineKeyboardButton("75%", callback_data='audio_volume_75'), InlineKeyboardButton("100%", callback_data='audio_volume_100')],
        [InlineKeyboardButton("Назад", callback_data='back_audio')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Меню управления питанием
def power_menu():
    keyboard = [
        [InlineKeyboardButton("Перезагрузка", callback_data='power_reboot')],
        [InlineKeyboardButton("Выключение", callback_data='power_shutdown')],
        [InlineKeyboardButton("Спящий режим", callback_data='power_sleep')],
        [InlineKeyboardButton("WOL", callback_data='power_wol')],
        [InlineKeyboardButton("Назад", callback_data='back_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Меню управления приложениями
def apps_menu():
    keyboard = [
        [InlineKeyboardButton("Открыть приложение", callback_data='apps_open')],
        [InlineKeyboardButton("Закрыть приложение", callback_data='apps_close')],
        [InlineKeyboardButton("Назад", callback_data='back_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Главное меню:", reply_markup=main_menu())

# Обработчик callback-запросов от кнопок
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'menu_audio':
        await query.edit_message_text(text="Меню аудио:", reply_markup=audio_menu())
    elif data == 'audio_playpause':
        try:
            subprocess.run("playerctl play-pause", shell=True)
            await query.answer(text="Команда Play/Pause выполнена")
        except Exception as e:
            await query.answer(text=f"Ошибка: {e}")
    elif data == 'audio_next':
        try:
            subprocess.run("playerctl next", shell=True)
            await query.answer(text="Следующий трек")
        except Exception as e:
            await query.answer(text=f"Ошибка: {e}")
    elif data == 'audio_prev':
        try:
            subprocess.run("playerctl previous", shell=True)
            await query.answer(text="Предыдущий трек")
        except Exception as e:
            await query.answer(text=f"Ошибка: {e}")
    elif data == 'audio_volume':
        await query.edit_message_text(text="Выберите уровень громкости:", reply_markup=volume_menu())
    elif data.startswith('audio_volume_'):
        vol = data.split('_')[-1]  # Получаем значение громкости, например "25", "50" и т.д.
        try:
            subprocess.run(f"amixer sset Master {vol}%", shell=True)
            await query.answer(text=f"Громкость установлена на {vol}%")
        except Exception as e:
            await query.answer(text=f"Ошибка: {e}")
    elif data == 'back_audio':
        await query.edit_message_text(text="Меню аудио:", reply_markup=audio_menu())
    elif data == 'menu_power':
        await query.edit_message_text(text="Меню питания:", reply_markup=power_menu())
    elif data == 'power_reboot':
        try:
            subprocess.run("reboot", shell=True)
            await query.answer(text="Перезагрузка")
        except Exception as e:
            await query.answer(text=f"Ошибка: {e}")
    elif data == 'power_shutdown':
        try:
            subprocess.run("shutdown now", shell=True)
            await query.answer(text="Выключение")
        except Exception as e:
            await query.answer(text=f"Ошибка: {e}")
    elif data == 'power_sleep':
        try:
            subprocess.run("systemctl suspend", shell=True)
            await query.answer(text="Переход в спящий режим")
        except Exception as e:
            await query.answer(text=f"Ошибка: {e}")
    elif data == 'power_wol':
        try:
            subprocess.run(f"wakeonlan {WOL_MAC}", shell=True)
            await query.answer(text="WOL пакет отправлен")
        except Exception as e:
            await query.answer(text=f"Ошибка: {e}")
    elif data == 'menu_apps':
        await query.edit_message_text(text="Меню приложений:", reply_markup=apps_menu())
    elif data == 'apps_open':
        context.user_data['action'] = 'open'
        await query.edit_message_text(text="Отправьте название или команду для открытия приложения:")
    elif data == 'apps_close':
        context.user_data['action'] = 'close'
        await query.edit_message_text(text="Отправьте название или команду для закрытия приложения:")
    elif data == 'menu_monitor':
        cpu_usage = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        mem_used = mem.used / (1024**3)
        mem_total = mem.total / (1024**3)
        try:
            result = subprocess.run("nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits",
                                      shell=True, capture_output=True, text=True)
            gpu_usage = result.stdout.strip().split('\n')[0] + "%" if result.stdout.strip() != "" else "N/A"
        except Exception:
            gpu_usage = "N/A"
        text = (f"Системный мониторинг:\n"
                f"CPU: {cpu_usage}%\n"
                f"GPU: {gpu_usage}\n"
                f"Память: {mem_used:.2f}GB / {mem_total:.2f}GB")
        await query.edit_message_text(text=text, reply_markup=main_menu())
    elif data == 'back_main':
        await query.edit_message_text(text="Главное меню:", reply_markup=main_menu())

# Обработчик текстовых сообщений для управления приложениями
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'action' in context.user_data:
        action = context.user_data.pop('action')
        app_command = update.message.text.strip()
        if action == 'open':
            try:
                subprocess.Popen(app_command, shell=True)
                await update.message.reply_text(f"Запуск: {app_command}", reply_markup=main_menu())
            except Exception as e:
                await update.message.reply_text(f"Ошибка при запуске: {e}", reply_markup=main_menu())
        elif action == 'close':
            try:
                subprocess.run(f"pkill -f '{app_command}'", shell=True)
                await update.message.reply_text(f"Закрытие: {app_command}", reply_markup=main_menu())
            except Exception as e:
                await update.message.reply_text(f"Ошибка при закрытии: {e}", reply_markup=main_menu())
    else:
        await update.message.reply_text("Пожалуйста, используйте кнопки для управления.", reply_markup=main_menu())

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == '__main__':
    main()
