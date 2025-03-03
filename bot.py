#!/usr/bin/env python3
import logging
import subprocess
import difflib
import os
import psutil
import shutil

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
)

# Определяем состояния диалога
MENU = 0
SSH_CONFIG = 1
PLAYER_SELECTION = 2
MUSIC = 3
MUSIC_VOLUME = 4
APP = 5
POWER = 6
MAC_INPUT = 7

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------------
# Вспомогательная функция для выполнения команд (локально или по SSH)
# -------------------------
def run_command(command: list, context: CallbackContext):
    ssh_target = context.user_data.get("ssh_target")
    if ssh_target:
        # Выполнение команды на удалённом хосте через SSH
        full_command = ["ssh", ssh_target] + command
        return subprocess.run(full_command, capture_output=True, text=True)
    else:
        return subprocess.run(command, capture_output=True, text=True)

# =========================
# Функции для установки SSH подключения
# =========================
def set_ssh(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Введите SSH адрес в формате user@host (например, user@192.168.1.100):")
    return SSH_CONFIG

def ssh_config(update: Update, context: CallbackContext) -> int:
    ssh_target = update.message.text.strip()
    context.user_data['ssh_target'] = ssh_target
    update.message.reply_text(f"SSH подключение установлено: {ssh_target}")
    return MENU

# =========================
# Функции для установки MAC адреса для Magic Packet
# =========================
def set_mac(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Введите MAC адрес для отправки Magic Packet (формат: XX:XX:XX:XX:XX:XX):")
    return MAC_INPUT

def mac_config(update: Update, context: CallbackContext) -> int:
    mac_address = update.message.text.strip()
    context.user_data['mac_address'] = mac_address
    update.message.reply_text(f"MAC адрес установлен: {mac_address}")
    return MENU

# =========================
# Функции для выбора плеера
# =========================
def get_active_players() -> list:
    """
    Получает список активных плееров через команду `playerctl -l`
    """
    try:
        result = run_command(["playerctl", "-l"], context=CallbackContext({}))
        players = result.stdout.strip().splitlines()
        return [p.strip() for p in players if p.strip()]
    except Exception as e:
        logger.error(f"Ошибка получения списка плееров: {e}")
        return []

def select_player(update: Update, context: CallbackContext) -> int:
    """
    Отправляет пользователю список активных плееров для выбора
    """
    players = get_active_players()
    if not players:
        update.message.reply_text("Нет активных плееров.")
        return MENU
    keyboard = [[InlineKeyboardButton(p, callback_data=f"select_player:{p}")] for p in players]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Выберите плеер для управления музыкой:", reply_markup=reply_markup)
    return PLAYER_SELECTION

def select_player_callback(update: Update, context: CallbackContext) -> int:
    """
    Обрабатывает выбор плеера пользователем.
    Сохраняет выбранный плеер в контексте и переходит в меню управления музыкой.
    """
    query = update.callback_query
    query.answer()
    player = query.data.split(":", 1)[1]
    context.user_data['player'] = player
    query.edit_message_text(f"Вы выбрали плеер: {player}")
    return music_menu_by_player(update, context)

def music_menu_by_player(update: Update, context: CallbackContext) -> int:
    """
    Отправляет пользователю меню управления музыкой для выбранного плеера.
    Добавлена кнопка для смены плеера.
    """
    keyboard = [
        [
            InlineKeyboardButton("Следующий трек", callback_data='music_next'),
            InlineKeyboardButton("Предыдущий трек", callback_data='music_prev')
        ],
        [InlineKeyboardButton("Пауза/Воспроизведение", callback_data='music_toggle')],
        [InlineKeyboardButton("Актуальный трек", callback_data='music_current')],
        [InlineKeyboardButton("Изменить громкость", callback_data='music_volume')],
        [InlineKeyboardButton("Сменить плеер", callback_data='change_player')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        update.callback_query.edit_message_text(
            "Управление музыкой для плеера: " + context.user_data.get('player', ''),
            reply_markup=reply_markup
        )
    else:
        update.message.reply_text(
            "Управление музыкой для плеера: " + context.user_data.get('player', ''),
            reply_markup=reply_markup
        )
    return MUSIC

# =========================
# Функции управления музыкой через playerctl
# =========================
def music_callback(update: Update, context: CallbackContext) -> int:
    """
    Обрабатывает нажатия кнопок управления музыкой.
    Выполняет команды для выбранного плеера с помощью playerctl.
    """
    query = update.callback_query
    query.answer()
    data = query.data

    if data == 'change_player':
        players = get_active_players()
        if not players:
            query.edit_message_text("Нет активных плееров для управления музыкой.")
            return MENU
        keyboard = [[InlineKeyboardButton(p, callback_data=f"select_player:{p}")] for p in players]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("Выберите плеер для управления музыкой:", reply_markup=reply_markup)
        return PLAYER_SELECTION

    player = context.user_data.get('player')
    if not player:
        query.edit_message_text("Плеер не выбран. Пожалуйста, выберите плеер.")
        return PLAYER_SELECTION

    if data == 'music_next':
        command = ["playerctl", "-p", player, "next"]
    elif data == 'music_prev':
        command = ["playerctl", "-p", player, "previous"]
    elif data == 'music_toggle':
        command = ["playerctl", "-p", player, "play-pause"]
    elif data == 'music_current':
        command = ["playerctl", "-p", player, "metadata", "--format", "{{ artist }} - {{ title }}"]
    elif data == 'music_volume':
        query.edit_message_text("Введите желаемую громкость (от 1 до 100):")
        return MUSIC_VOLUME
    else:
        query.edit_message_text("Неизвестное действие.")
        return MUSIC

    try:
        result = run_command(command, context)
        output = result.stdout.strip() or "Команда выполнена."
        query.edit_message_text(output)
    except Exception as e:
        logger.error(f"Ошибка при выполнении команды {' '.join(command)}: {e}")
        query.edit_message_text("Ошибка при выполнении команды.")
    return MUSIC

def music_volume(update: Update, context: CallbackContext) -> int:
    """
    Обрабатывает ввод значения громкости.
    Переводит процентное значение в дробное (0-1) и устанавливает громкость для выбранного плеера.
    """
    player = context.user_data.get('player')
    if not player:
        update.message.reply_text("Плеер не выбран. Сначала выберите плеер.")
        return PLAYER_SELECTION
    try:
        volume_percent = int(update.message.text)
        if not (1 <= volume_percent <= 100):
            update.message.reply_text("Пожалуйста, введите число от 1 до 100.")
            return MUSIC_VOLUME
    except ValueError:
        update.message.reply_text("Неверный ввод. Введите число от 1 до 100.")
        return MUSIC_VOLUME

    volume_fraction = volume_percent / 100.0
    command = ["playerctl", "-p", player, "volume", str(volume_fraction)]
    try:
        result = run_command(command, context)
        output = result.stdout.strip() or f"Громкость изменена на {volume_percent}%."
        update.message.reply_text(output)
    except Exception as e:
        logger.error(f"Ошибка при выполнении команды {' '.join(command)}: {e}")
        update.message.reply_text("Ошибка при выполнении команды.")
    return MUSIC

# =========================
# Функция управления приложениями
# =========================
def app_control(update: Update, context: CallbackContext) -> int:
    """
    Открытие или закрытие приложений.
    Ожидается ввод в формате: open <название> или close <название>
    Теперь бот ищет приложение непосредственно в системе.
    """
    text = update.message.text.strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        update.message.reply_text("Неверный формат. Используйте: open <название> или close <название>")
        return APP

    action, app_name = parts[0].lower(), parts[1].lower()

    if action == "open":
        if context.user_data.get("ssh_target"):
            update.message.reply_text("Запуск приложений через SSH не поддерживается.")
            return APP
        executable = shutil.which(app_name)
        if not executable:
            update.message.reply_text("Приложение не найдено в системе.")
            return APP
        try:
            subprocess.Popen([executable])
            update.message.reply_text(f"Приложение {app_name} запущено.")
        except Exception as e:
            logger.error(f"Ошибка при запуске {app_name}: {e}")
            update.message.reply_text(f"Ошибка при запуске {app_name}.")
    elif action == "close":
        try:
            run_command(["pkill", "-f", app_name], context)
            update.message.reply_text(f"Приложение {app_name} закрыто.")
        except Exception as e:
            logger.error(f"Ошибка при закрытии {app_name}: {e}")
            update.message.reply_text(f"Ошибка при закрытии {app_name}.")
    else:
        update.message.reply_text("Неверное действие. Используйте open или close.")
    return MENU

# =========================
# Функции управления питанием
# =========================
def power_menu(update: Update, context: CallbackContext) -> int:
    """Показываем меню управления питанием ПК."""
    keyboard = [
        [InlineKeyboardButton("Выключение", callback_data='power_shutdown')],
        [InlineKeyboardButton("Перезагрузка", callback_data='power_reboot')],
        [InlineKeyboardButton("Отправка Magic Packet", callback_data='power_magic')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        update.message.reply_text("Выберите действие управления питанием:", reply_markup=reply_markup)
    elif update.callback_query:
        update.callback_query.edit_message_text("Выберите действие управления питанием:", reply_markup=reply_markup)
    return POWER

def power_callback(update: Update, context: CallbackContext) -> int:
    """Обработка выбора в меню управления питанием."""
    query = update.callback_query
    query.answer()
    data = query.data

    if data == "power_shutdown":
        try:
            run_command(["shutdown", "now"], context)
            query.edit_message_text("Система выключается...")
        except Exception as e:
            logger.error(f"Ошибка при выключении: {e}")
            query.edit_message_text("Ошибка при выполнении выключения.")
    elif data == "power_reboot":
        try:
            run_command(["reboot"], context)
            query.edit_message_text("Система перезагружается...")
        except Exception as e:
            logger.error(f"Ошибка при перезагрузке: {e}")
            query.edit_message_text("Ошибка при выполнении перезагрузки.")
    elif data == "power_magic":
        mac_address = context.user_data.get("mac_address")
        if not mac_address:
            query.edit_message_text("MAC адрес не установлен. Используйте команду /setmac для установки.")
            return MENU
        try:
            run_command(["wakeonlan", mac_address], context)
            query.edit_message_text("Magic Packet отправлен.")
        except Exception as e:
            logger.error(f"Ошибка при отправке Magic Packet: {e}")
            query.edit_message_text("Ошибка при отправке Magic Packet.")
    return MENU

# =========================
# Функция получения системной информации
# =========================
def system_info(update: Update, context: CallbackContext) -> int:
    """Получение информации о системе: загрузка CPU, памяти и GPU."""
    try:
        cpu_usage = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        mem_usage = mem.percent

        try:
            gpu_proc = run_command(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                context
            )
            gpu_usage = gpu_proc.stdout.strip() + "%" if gpu_proc.stdout.strip() else "N/A"
        except Exception:
            gpu_usage = "N/A"

        info = (
            f"Информация о системе:\n"
            f"CPU: {cpu_usage}%\n"
            f"Память: {mem_usage}%\n"
            f"GPU: {gpu_usage}"
        )
        update.message.reply_text(info)
    except Exception as e:
        logger.error(f"Ошибка при получении системной информации: {e}")
        update.message.reply_text("Ошибка при получении информации о системе.")
    return MENU

# =========================
# Главное меню
# =========================
def start(update: Update, context: CallbackContext) -> int:
    """Обработчик команды /start. Показывает главное меню."""
    keyboard = [
        [InlineKeyboardButton("Управление музыкой", callback_data='menu_music')],
        [InlineKeyboardButton("Управление приложениями", callback_data='menu_app')],
        [InlineKeyboardButton("Управление питанием", callback_data='menu_power')],
        [InlineKeyboardButton("Системная информация", callback_data='menu_sysinfo')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Главное меню:", reply_markup=reply_markup)
    return MENU

def menu_callback(update: Update, context: CallbackContext) -> int:
    """Обработка нажатий в главном меню."""
    query = update.callback_query
    query.answer()
    data = query.data

    if data == 'menu_music':
        players = get_active_players()
        if not players:
            query.edit_message_text("Нет активных плееров для управления музыкой.")
            return MENU
        keyboard = [[InlineKeyboardButton(p, callback_data=f"select_player:{p}")] for p in players]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text("Выберите плеер для управления музыкой:", reply_markup=reply_markup)
        return PLAYER_SELECTION
    elif data == 'menu_app':
        query.edit_message_text("Введите команду для управления приложениями (например: open firefox или close vlc):")
        return APP
    elif data == 'menu_power':
        return power_menu(update, context)
    elif data == 'menu_sysinfo':
        return system_info(update, context)
    else:
        query.edit_message_text("Неизвестное действие.")
        return MENU

# =========================
# Основная функция
# =========================
def main():
    # Если переменная окружения не задана, запрашиваем токен в консоли
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        TOKEN = input("Введите токен Telegram бота: ").strip()

    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    # Основной ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [
                CallbackQueryHandler(menu_callback, pattern="^menu_")
            ],
            PLAYER_SELECTION: [
                CallbackQueryHandler(select_player_callback, pattern="^select_player:")
            ],
            MUSIC: [
                CallbackQueryHandler(music_callback, pattern="^(music_|change_player)")
            ],
            MUSIC_VOLUME: [
                MessageHandler(Filters.text & ~Filters.command, music_volume)
            ],
            APP: [
                MessageHandler(Filters.text & ~Filters.command, app_control)
            ],
            POWER: [
                CallbackQueryHandler(power_callback, pattern="^power_")
            ],
        },
        fallbacks=[CommandHandler("start", start)]
    )

    dispatcher.add_handler(conv_handler)

    # Отдельные ConversationHandler для настройки SSH и MAC адреса
    ssh_handler = ConversationHandler(
        entry_points=[CommandHandler("setssh", set_ssh)],
        states={
            SSH_CONFIG: [MessageHandler(Filters.text & ~Filters.command, ssh_config)]
        },
        fallbacks=[CommandHandler("cancel", start)]
    )
    dispatcher.add_handler(ssh_handler)

    mac_handler = ConversationHandler(
        entry_points=[CommandHandler("setmac", set_mac)],
        states={
            MAC_INPUT: [MessageHandler(Filters.text & ~Filters.command, mac_config)]
        },
        fallbacks=[CommandHandler("cancel", start)]
    )
    dispatcher.add_handler(mac_handler)

    updater.start_polling()
    logger.info("Бот запущен.")
    updater.idle()

if __name__ == "__main__":
    main()
