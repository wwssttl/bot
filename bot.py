import logging
import subprocess
import asyncio
import psutil
import os
import re
import signal
from wakeonlan import send_magic_packet
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ForceReply
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram.error import TelegramError

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Идентификатор администратора (замените на ваш реальный ID)
ADMIN_ID = 6061771975  # Замените на ваш Telegram ID

# Словарь для хранения текущего меню пользователя
current_menu = {}

# Пороговые значения для уведомлений
CPU_LOAD_THRESHOLD = 85  # Процент нагрузки
GPU_LOAD_THRESHOLD = 85  # Процент нагрузки (требует реализации)
CPU_TEMP_THRESHOLD = 75  # Градусы Цельсия
GPU_TEMP_THRESHOLD = 75  # Градусы Цельсия (требует реализации)

# ==================== СЛУЖЕБНЫЕ ФУНКЦИИ ====================

async def execute_command(command: list, success_msg: str, update: Update, menu: callable):
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            await send_response(update, f"✅ {success_msg}", menu)
        else:
            error_msg = stderr.decode().strip() if stderr else "Неизвестная ошибка"
            logger.error(f"Ошибка команды {command}: {error_msg}")
            await send_response(update, f"❌ Ошибка: {error_msg}", menu)
    except Exception as e:
        logger.error(f"Ошибка выполнения команды {command}: {e}")
        await send_response(update, f"❌ Ошибка выполнения команды: {e}", menu)


async def send_response(update: Update, text: str, menu: callable = None):
    if not menu:
        menu = current_menu.get(update.effective_user.id, main_menu)
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=menu() if menu else None
            )
        elif update.message:
            await update.message.reply_text(text, reply_markup=menu() if menu else None)
        else:
            logger.warning("Нет доступного поля для отправки сообщения.")
    except TelegramError as e:
        logger.error(f"Ошибка отправки сообщения: {e}")


def find_app_executable(app_name: str):
    try:
        # Поиск с помощью which
        result = subprocess.run(
            ["which", app_name],
            capture_output=True,
            text=True
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception as e:
        logger.error(f"Ошибка поиска приложения '{app_name}': {e}")
        return None


async def manage_app_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await manage_app(update, context, "start")


async def manage_app_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await manage_app(update, context, "stop")


async def manage_app(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        if update.message:
            await update.message.reply_text("⛔ Доступ запрещен!")
        return
    try:
        if not context.args:
            await send_response(update, "❌ Укажите название приложения!", apps_menu)
            return

        app_name = " ".join(context.args).strip()

        # Проверка наличия приложения
        app_path = find_app_executable(app_name)
        if not app_path:
            await send_response(update, f"❌ Приложение '{app_name}' не найдено.", apps_menu)
            return

        # Получение текущего DISPLAY и XAUTHORITY
        display = os.environ.get('DISPLAY', ':0')
        xauth = os.environ.get('XAUTHORITY', f"/home/{os.environ.get('USER')}/.Xauthority")

        env = dict(os.environ, DISPLAY=display, XAUTHORITY=xauth)

        if action == "start":
            try:
                # Запуск приложения в новом сеансе
                proc = await asyncio.create_subprocess_exec(
                    app_path,
                    env=env,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=True
                )
                await send_response(update, f"✅ Запускаю '{app_name}'...", apps_menu)
            except Exception as e:
                logger.error(f"Ошибка запуска приложения '{app_name}': {e}")
                await send_response(update, f"❌ Ошибка запуска: {e}", apps_menu)

        elif action == "stop":
            try:
                # Подтверждение от пользователя
                await send_response(
                    update,
                    f"⚠️ Вы уверены, что хотите завершить все процессы '{app_name}'?\nОтветьте 'yes' или 'no'.",
                    None
                )
                context.user_data['pending_kill'] = {
                    'app_name': app_name,
                    'menu': apps_menu
                }
            except Exception as e:
                logger.error(f"Ошибка подготовки к остановке приложения '{app_name}': {e}")
                await send_response(update, f"❌ Ошибка: {e}", apps_menu)

    except Exception as e:
        logger.error(f"Ошибка управления приложением: {e}")
        await send_response(update, f"❌ Ошибка: {e}", apps_menu)


async def confirm_kill_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_response = update.message.text.lower()
    pending = context.user_data.get('pending_kill')
    if pending and user_response in ['yes', 'да', 'y', 'д']:
        app_name = pending['app_name']
        try:
            # Завершение процессов приложения
            proc = await asyncio.create_subprocess_exec(
                "pkill", "-f", app_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.wait()
            if proc.returncode == 0:
                await send_response(update, f"✅ Завершены все процессы '{app_name}'.", apps_menu)
            else:
                stderr = await proc.stderr.read()
                error_msg = stderr.decode().strip() if stderr else "Не удалось завершить процессы."
                await send_response(update, f"❌ Ошибка остановки: {error_msg}", apps_menu)
        except Exception as e:
            logger.error(f"Ошибка остановки приложения '{app_name}': {e}")
            await send_response(update, f"❌ Ошибка остановки: {e}", apps_menu)
        context.user_data['pending_kill'] = None
    else:
        await send_response(update, "🚫 Действие отменено.", pending['menu'])
        context.user_data['pending_kill'] = None


# ==================== МЕНЮ И КЛАВИАТУРЫ ====================

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎵 Управление музыкой", callback_data="music_menu")],
        [InlineKeyboardButton("📦 Управление приложениями", callback_data="apps_menu")],
        [InlineKeyboardButton("🔌 Управление питанием", callback_data="power_menu")],
        [InlineKeyboardButton("⚙️ Системные функции", callback_data="system_menu")]
    ])


def music_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Воспроизвести", callback_data="music_play"),
         InlineKeyboardButton("⏸ Пауза", callback_data="music_pause")],
        [InlineKeyboardButton("⏭ Следующий", callback_data="music_next"),
         InlineKeyboardButton("⏮ Предыдущий", callback_data="music_previous")],
        [InlineKeyboardButton("🎵 Текущая песня", callback_data="music_current")],
        [InlineKeyboardButton("🔄 Выбрать плеер", callback_data="music_choose_player")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ])


def apps_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Запустить приложение", callback_data="app_start")],
        [InlineKeyboardButton("📝 Остановить приложение", callback_data="app_stop")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ])


def power_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Перезагрузка", callback_data="power_reboot")],
        [InlineKeyboardButton("⏻ Выключение", callback_data="power_shutdown")],
        [InlineKeyboardButton("🌙 Спящий режим", callback_data="power_suspend")],
        [InlineKeyboardButton("💻 Включить ПК (WoL)", callback_data="power_wakeonlan")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ])


def system_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика системы", callback_data="sys_info")],
        [InlineKeyboardButton("🔊 Установить громкость", callback_data="sys_vol_set")],
        [InlineKeyboardButton("🔇 Переключить звук", callback_data="sys_vol_mute")],
        [InlineKeyboardButton("⚠️ Уведомления о нагрузке и температуре", callback_data="sys_alerts")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ])


# ==================== ОБРАБОТЧИКИ СОБЫТИЙ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Попытка входа: ID={user_id}, Ожидаемый ID={ADMIN_ID}")

    if user_id != ADMIN_ID:
        if update.message:
            await update.message.reply_text(f"⛔ Доступ запрещен! Ваш ID: {user_id}")
        return

    current_menu[user_id] = main_menu
    if update.message:
        await update.message.reply_text(
            "🤖 Бот для управления компьютером\nВыберите раздел:",
            reply_markup=main_menu()
        )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        logger.warning("Нет callback_query в обновлении.")
        return

    await query.answer()
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await query.edit_message_text("⛔ Доступ запрещен!")
        return

    data = query.data

    if data == "main_menu":
        current_menu[user_id] = main_menu
        await query.edit_message_text("Главное меню:", reply_markup=main_menu())
        return

    menus = {
        "music_menu": (music_menu, "Управление музыкой"),
        "apps_menu": (apps_menu, "Управление приложениями"),
        "power_menu": (power_menu, "Управление питанием"),
        "system_menu": (system_menu, "Системные функции")
    }

    if data in menus:
        menu_func, title = menus[data]
        current_menu[user_id] = menu_func
        await query.edit_message_text(f"🔧 {title}:", reply_markup=menu_func())
        return

    try:
        await query.edit_message_text("🔄 Обработка...", reply_markup=None)

        if data.startswith("music_"):
            action = data.split("_", 1)[1]
            await handle_music_action(update, context, action)

        elif data.startswith("power_"):
            await handle_power_action(update, context, data)

        elif data.startswith("sys_"):
            await handle_system_action(update, context, data)

        elif data == "app_start":
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Введите команду в формате /start_app <имя_приложения>",
                reply_markup=ForceReply(selective=True)
            )
        elif data == "app_stop":
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Введите команду в формате /stop_app <имя_приложения>",
                reply_markup=ForceReply(selective=True)
            )
        else:
            await send_response(update, "❌ Неизвестная команда.", main_menu)

    except Exception as e:
        logger.error(f"Ошибка обработки кнопки: {e}")
        await send_response(update, f"❌ Ошибка выполнения: {e}", main_menu)


async def handle_music_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    try:
        # Проверка наличия playerctl
        result = subprocess.run(["which", "playerctl"], capture_output=True)
        if result.returncode != 0:
            await send_response(update, "❌ Утилита 'playerctl' не установлена.", music_menu)
            return

        # Получение списка плееров
        players_output = subprocess.check_output(["playerctl", "-l"], text=True)
        all_players = players_output.strip().split('\n')

        # Фильтрация плееров: исключаем 'mpv', выбираем 'chromium.instance'
        players = [
            player for player in all_players
            if player and player != 'mpv' and player.startswith('chromium.instance')
        ]

        if not players:
            await send_response(update, "❌ Нет доступных плееров.", music_menu)
            return

        # Проверяем, выбран ли плеер пользователем
        selected_player = context.user_data.get('selected_player')

        if action == "choose_player":
            # Предлагаем выбрать плеер
            buttons = [
                [InlineKeyboardButton(player, callback_data=f"select_player_{player}")]
                for player in players
            ]
            buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="music_menu")])
            reply_markup = InlineKeyboardMarkup(buttons)
            await send_response(update, "Выберите плеер:", lambda: reply_markup)
            return

        elif action.startswith("select_player_"):
            # Пользователь выбрал плеер
            selected_player = action.replace("select_player_", "")
            context.user_data['selected_player'] = selected_player
            await send_response(update, f"🎵 Выбран плеер: {selected_player}", music_menu)
            return

        if not selected_player or selected_player not in players:
            # Если плеер не выбран или недоступен, предлагаем выбрать
            context.user_data['selected_player'] = None
            # Если один плеер, выбираем его автоматически
            if len(players) == 1:
                selected_player = players[0]
                context.user_data['selected_player'] = selected_player
            else:
                # Предлагаем выбрать плеер
                buttons = [
                    [InlineKeyboardButton(player, callback_data=f"select_player_{player}")]
                    for player in players
                ]
                buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="music_menu")])
                reply_markup = InlineKeyboardMarkup(buttons)
                await send_response(update, "Выберите плеер:", lambda: reply_markup)
                return

        if action == "current":
            # Получение информации о текущей песне
            proc = await asyncio.create_subprocess_exec(
                "playerctl", "-p", selected_player, "metadata", "--format", "{{ artist }} - {{ title }}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate()
            song_info = stdout.decode().strip()
            if song_info:
                await send_response(update, f"🎶 Сейчас играет: {song_info}", music_menu)
                return
            else:
                await send_response(update, "❌ Не удалось получить информацию о текущей песне.", music_menu)
        else:
            # Управление воспроизведением
            proc = await asyncio.create_subprocess_exec(
                "playerctl", "-p", selected_player, action,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.wait()
            await send_response(update, f"🎵 Команда '{action}' выполнена для плеера '{selected_player}'.", music_menu)
    except Exception as e:
        logger.error(f"Ошибка управления музыкой: {e}")
        await send_response(update, f"❌ Ошибка: {e}", music_menu)


async def handle_power_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    commands = {
        "power_reboot": ["sudo", "/sbin/reboot"],
        "power_shutdown": ["sudo", "/sbin/shutdown", "now"],
        "power_suspend": ["systemctl", "suspend"]
    }

    if action == "power_wakeonlan":
        await send_wakeonlan(update, context)
        return

    command = commands.get(action)
    if not command:
        await send_response(update, "❌ Неизвестная команда питания.", power_menu)
        return

    # Подтверждение от пользователя
    await send_response(
        update,
        f"⚠️ Вы уверены, что хотите выполнить '{action}'?\nОтветьте 'yes' или 'no'.",
        None
    )

    # Сохранение ожидаемой команды для подтверждения
    context.user_data['pending_command'] = {
        'command': command,
        'menu': power_menu
    }


async def confirm_power_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_response = update.message.text.lower()
    pending = context.user_data.get('pending_command')
    if pending and user_response in ['yes', 'да', 'y', 'д']:
        await execute_command(pending['command'], "Команда выполнена.", update, pending['menu'])
        context.user_data['pending_command'] = None
    else:
        await send_response(update, "🚫 Действие отменено.", pending['menu'])
        context.user_data['pending_command'] = None


async def handle_system_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    if action == "sys_info":
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory().percent
        await send_response(update, f"📊 Статистика:\nCPU: {cpu}%\nRAM: {mem}%", system_menu)
    elif action == "sys_vol_mute":
        await execute_command(
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
            "🔇 Звук переключен.",
            update,
            system_menu
        )
    elif action == "sys_vol_set":
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Введите уровень громкости (0-150):",
            reply_markup=ForceReply(selective=True)
        )
    elif action == "sys_alerts":
        # Запуск мониторинга системы
        if not context.job_queue.get_jobs_by_name('system_monitor'):
            context.job_queue.run_repeating(
                monitor_system,
                interval=60,
                first=0,
                chat_id=update.effective_chat.id,
                name='system_monitor'
            )
            await send_response(update, "📡 Мониторинг системы запущен. Вы будете получать уведомления о высокой нагрузке и температуре.", system_menu)
        else:
            # Остановка мониторинга
            jobs = context.job_queue.get_jobs_by_name('system_monitor')
            for job in jobs:
                job.schedule_removal()
            await send_response(update, "📡 Мониторинг системы остановлен.", system_menu)


async def set_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        if update.message:
            await update.message.reply_text("⛔ Доступ запрещен!")
        return
    try:
        volume = int(update.message.text)
        if 0 <= volume <= 150:
            await execute_command(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
                f"🔊 Громкость установлена на {volume}%.",
                update,
                system_menu
            )
        else:
            await send_response(update, "❌ Укажите значение от 0 до 150.", system_menu)
    except ValueError:
        await send_response(update, "❌ Неверный формат числа.", system_menu)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        if update.message:
            await update.message.reply_text("⛔ Доступ запрещен!")
        return
    text = update.message.text.strip().lower()
    pending_kill = context.user_data.get('pending_kill')
    pending_power = context.user_data.get('pending_command')

    if pending_kill:
        # Обработка подтверждения завершения приложения
        await confirm_kill_app(update, context)
    elif pending_power:
        # Обработка подтверждения действия питания
        await confirm_power_action(update, context)
    else:
        if text.startswith('/start_app'):
            await manage_app_start(update, context)
        elif text.startswith('/stop_app'):
            await manage_app_stop(update, context)
        elif re.match(r'^\d+$', text):
            # Обработка установки громкости
            await set_volume(update, context)
        else:
            if update.message:
                await update.message.reply_text("❌ Неизвестная команда.")


async def monitor_system(context: ContextTypes.DEFAULT_TYPE):
    # Проверка нагрузки CPU
    cpu_load = psutil.cpu_percent(interval=1)
    if cpu_load > CPU_LOAD_THRESHOLD:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Высокая нагрузка CPU: {cpu_load}%"
        )

    # Проверка температуры CPU
    try:
        temps = psutil.sensors_temperatures()
        if 'coretemp' in temps:
            cpu_temp = max([t.current for t in temps['coretemp']])
            if cpu_temp > CPU_TEMP_THRESHOLD:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🌡️ Высокая температура CPU: {cpu_temp}°C"
                )
    except AttributeError:
        logger.warning("Сбор данных о температуре не поддерживается на этой платформе.")

    # Проверка нагрузки и температуры GPU (требует дополнительной реализации для конкретного оборудования)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    logger.error(f"Ошибка: {error}")
    if update:
        await send_response(update, f"⚠️ Произошла ошибка: {error}", None)


async def send_wakeonlan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Замените на MAC-адрес вашего целевого компьютера
    TARGET_MAC_ADDRESS = "b0:6e:bf:c8:3e:ba"  # Укажите ваш MAC-адрес

    try:
        send_magic_packet(TARGET_MAC_ADDRESS)
        await send_response(update, f"💡 Magic packet отправлен на {TARGET_MAC_ADDRESS}. Попытка включить ПК.", power_menu)
    except Exception as e:
        logger.error(f"Ошибка отправки magic packet: {e}")
        await send_response(update, f"❌ Ошибка отправки magic packet: {e}", power_menu)


def main():
    # Создание экземпляра приложения
    application = Application.builder().token("8137824543:AAGKP32Rjj_ctA5horpEVoKOezJSBNhsRfg").build()

    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("start_app", manage_app_start))
    application.add_handler(CommandHandler("stop_app", manage_app_stop))

    # Регистрация обработчиков сообщений и колбэков
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Глобальный обработчик ошибок
    application.add_error_handler(error_handler)

    # Запуск бота
    application.run_polling()


if __name__ == "__main__":
    main()
