import logging
import subprocess
import difflib
import psutil
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (Updater, CommandHandler, CallbackContext,
                          CallbackQueryHandler, MessageHandler, Filters)

# Настройка логирования для анализа ошибок
logging.basicConfig(filename='bot.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s:%(message)s')

# Список приложений для управления (можно расширять)
APP_LIST = ["firefox", "libreoffice", "vlc", "gedit", "thunderbird"]

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Добро пожаловать!\nДоступные команды:\n"
        "/music - управление музыкой\n"
        "/apps - управление приложениями\n"
        "/power - управление питанием ПК\n"
        "/sysdata - получение данных о системе"
    )

# Функция для проверки активного плеера
def ignore_mvn():
    try:
        result = subprocess.run(
            ["playerstl", "current"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=True
        )
        current_track = result.stdout.strip()
        # Если в ответе обнаружено 'mvn' – команды для музыки игнорируются
        return "mvn" in current_track.lower()
    except Exception as e:
        logging.error("Ошибка проверки плеера: %s", e)
        return False

# -------------------- Управление музыкой --------------------

def music_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Предыдущий трек", callback_data='prev'),
         InlineKeyboardButton("Пауза/Воспроизведение", callback_data='play_pause')],
        [InlineKeyboardButton("Следующий трек", callback_data='next'),
         InlineKeyboardButton("Актуальный трек", callback_data='current')],
        [InlineKeyboardButton("Изменить громкость", callback_data='volume')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Управление музыкой:", reply_markup=reply_markup)

def music_button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    # Если активен плеер mvn – игнорируем команды
    if ignore_mvn():
        query.edit_message_text(text="Команда проигнорирована, так как активен плеер mvn.")
        return

    try:
        if data == 'prev':
            subprocess.run(["playerstl", "prev"], check=True)
            query.edit_message_text(text="Запущен предыдущий трек.")
        elif data == 'play_pause':
            subprocess.run(["playerstl", "toggle"], check=True)
            query.edit_message_text(text="Пауза/Воспроизведение переключено.")
        elif data == 'next':
            subprocess.run(["playerstl", "next"], check=True)
            query.edit_message_text(text="Запущен следующий трек.")
        elif data == 'current':
            result = subprocess.run(["playerstl", "current"], check=True, stdout=subprocess.PIPE)
            track_info = result.stdout.decode().strip()
            query.edit_message_text(text=f"Актуальный трек: {track_info}")
        elif data == 'volume':
            query.edit_message_text(text="Введите уровень громкости (1-100):")
            context.user_data['awaiting_volume'] = True
        else:
            query.edit_message_text(text="Неизвестная команда.")
    except Exception as e:
        logging.error("Ошибка в управлении музыкой: %s", e)
        query.edit_message_text(text="Ошибка выполнения команды.")

# -------------------- Обработка ввода для ожидания (громкость, magic-пакет) --------------------

def handle_pending(update: Update, context: CallbackContext):
    # Если ожидается ввод уровня громкости
    if context.user_data.get('awaiting_volume'):
        try:
            vol = int(update.message.text)
            if 1 <= vol <= 100:
                if ignore_mvn():
                    update.message.reply_text("Команда проигнорирована, так как активен плеер mvn.")
                else:
                    subprocess.run(["playerstl", "volume", str(vol)], check=True)
                    update.message.reply_text(f"Громкость установлена на {vol}%.")
            else:
                update.message.reply_text("Введите число от 1 до 100.")
        except Exception as e:
            logging.error("Ошибка установки громкости: %s", e)
            update.message.reply_text("Ошибка установки громкости.")
        finally:
            context.user_data['awaiting_volume'] = False
        return

    # Если ожидается ввод MAC-адреса для magic-пакета
    if context.user_data.get('awaiting_magic'):
        mac = update.message.text.strip()
        try:
            subprocess.run(["wakeonlan", mac], check=True)
            update.message.reply_text(f"Magic пакет отправлен для {mac}.")
        except Exception as e:
            logging.error("Ошибка отправки magic пакета: %s", e)
            update.message.reply_text("Ошибка отправки magic пакета.")
        finally:
            context.user_data['awaiting_magic'] = False
        return

# -------------------- Управление приложениями --------------------

def app_manage(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Введите команду в формате:\nopen <имя_приложения> или close <имя_приложения>."
    )

def app_command(update: Update, context: CallbackContext):
    try:
        text = update.message.text.split()
        if len(text) < 2:
            update.message.reply_text("Неверный формат. Пример: open firefox")
            return
        action, app_name = text[0].lower(), text[1].lower()
        if action == "open":
            if app_name in APP_LIST:
                subprocess.Popen([app_name])
                update.message.reply_text(f"Запущено приложение: {app_name}.")
            else:
                suggestions = difflib.get_close_matches(app_name, APP_LIST)
                suggestion_text = ", ".join(suggestions) if suggestions else "нет подсказок"
                update.message.reply_text(
                    f"Приложение не найдено. Может, вы имели ввиду: {suggestion_text}?"
                )
        elif action == "close":
            if app_name in APP_LIST:
                subprocess.run(["pkill", app_name])
                update.message.reply_text(f"Закры
