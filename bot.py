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
MENU, PLAYER_SELECTION, MUSIC, MUSIC_VOLUME, APP, POWER = range(6)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================
# Функции для выбора плеера
# =========================

def get_active_players() -> list:
    """
    Получает список активных плееров через команду `playerctl -l`
    """
    try:
        result = subprocess.run(["playerctl", "-l"], capture_output=True, text=True)
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

    # Если нажата кнопка "Сменить плеер", переходим к выбору
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
        result = subprocess.run(command, capture_output=True, text=True)
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
        result = subprocess.run(command, capture_output=True, text=True)
        output = result.stdout.strip() or f"Громкость изменена на {volume_percent}%."
        update.message.reply_text(output)
    except Exception as e:
        logger.error(f"Ошибка при выполнении команды {' '.join(command)}: {e}")
        update.message.reply_text("Ошибка при выполнении команды.")
    return MUSIC

# =========================
# Функции управления приложениями
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
            subprocess.run(["pkill", "-f", app_name])
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
            subprocess.run(["shutdown", "now"])
            query.edit_message_text("Система выключается...")
        except Exception as e:
            logger.error(f"Ошибка при выключении: {e}")
            qu
