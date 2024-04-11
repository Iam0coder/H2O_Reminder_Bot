import telebot
import datetime
import time
import threading
import random
import json
from datetime import datetime, timedelta, timezone
import requests

TOKEN = '[API KEY]'
bot = telebot.TeleBot(TOKEN)
data_file = './user_data.json'
user_states = {}
reminder_thread_running = False
reminder_thread_lock = threading.Lock()


def load_user_data():
    try:
        with open(data_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_user_data(data):
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=4)


user_data = load_user_data()


def update_user_data(chat_id, key, value):
    chat_id = str(chat_id)  # Ensure chat_id is string for JSON keys
    if chat_id not in user_data:
        user_data[chat_id] = {}
    user_data[chat_id][key] = value
    save_user_data(user_data)


def get_user_data(chat_id, key, default=None):
    chat_id = str(chat_id)
    return user_data.get(chat_id, {}).get(key, default)


@bot.message_handler(commands=['start'])
def start_message(message):
    global reminder_thread_running
    with reminder_thread_lock:
        reminder_thread_running = False
    # Ожидание, чтобы дать возможность текущему потоку завершиться
    time.sleep(1)
    chat_id = message.chat.id
    bot.reply_to(message,
                 f"Привет, {message.from_user.first_name}! Я чат-бот, который будет напоминать тебе пить воду.")
    if str(chat_id) not in user_data:
        update_user_data(chat_id, 'reminders', ['09:00', '14:00', '18:00'])
        update_user_data(chat_id, 'time_zone', 0)
        update_user_data(chat_id, 'water_intake', 0)
        update_user_data(chat_id, 'daily_goal', 2)  # Цель в литрах
        update_user_data(chat_id, 'dnd', False)
    with reminder_thread_lock:
        reminder_thread_running = True
    reminder_thread = threading.Thread(target=send_reminders)
    reminder_thread.daemon = True
    reminder_thread.start()


@bot.message_handler(commands=['help'])
def help_message(message):
    help_text = ("Вот команды, которые ты можешь использовать:\n"
                 "/start - Зарегистрироваться и начать получать напоминания о приеме воды.\n"
                 "/fact - Получить случайный факт о воде.\n"
                 "/settime - Установить предпочтительное время для напоминаний (формат: ЧЧ:ММ, через запятую).\n"
                 "/timezone - Установить свой часовой пояс (например, +3 для Москвы).\n"
                 "/drink - Записать выпитый стакан воды.\n"
                 "/stats - Посмотреть статистику потребления воды.\n"
                 "/goal - Установить цель по потреблению воды за день (в литрах).\n"
                 "/dnd - Включить/выключить режим 'Не беспокоить' (формат: ЧЧ:ММ-ЧЧ:ММ для активного периода).")
    bot.reply_to(message, help_text)


@bot.message_handler(commands=['drink'])
def drink_message(message):
    water_intake = get_user_data(message.chat.id, 'water_intake', 0) + 0.25  # Предполагаем, что стакан воды это 250 мл
    update_user_data(message.chat.id, 'water_intake', water_intake)
    bot.reply_to(message, f"Записано. Вы выпили уже {water_intake} литра(ов) воды сегодня.")


@bot.message_handler(commands=['stats'])
def stats_message(message):
    water_intake = get_user_data(message.chat.id, 'water_intake', 0)
    daily_goal = get_user_data(message.chat.id, 'daily_goal', 2)
    bot.reply_to(message, f"Сегодня вы выпили {water_intake} литров воды. Ваша цель {daily_goal} литров в день.")


@bot.message_handler(commands=['fact'])
def fact_message(message):
    facts = [
        "Вода - единственное вещество на Земле, которое существует в трех состояниях: твердом, жидком и газообразном",
        "Более 97% воды на Земле соленая",
        "Только 2,5% воды на Земле - пресная, и большая часть из нее заморожена в ледниках",
        "Средний человек может прожить без еды более месяца, но без воды - только около недели",
        "Горячая вода замерзает быстрее холодной воды под некоторыми условиями, эффект известный как эффект Мпемба",
        "Вода составляет около 60% веса взрослого человеческого тела",
        "Вода - универсальный растворитель, растворяющий больше веществ, чем любая другая жидкость",
        "Вода имеет аномально высокую точку кипения и температуру замерзания по сравнению с другими соединениями "
        "аналогичной молекулярной массы",
        "При замерзании вода расширяется на 9%, что делает лед менее плотным, чем вода",
        "Люди исследовали менее 5% мирового океана"
    ]
    random_fact = random.choice(facts)
    bot.reply_to(message, 'Лови факт о воде: ' + random_fact)


@bot.message_handler(commands=['settime'])
def settime_message(message):
    chat_id = message.chat.id
    safe_send_message(chat_id,
                      "Укажите время для напоминаний в формате ЧЧ:ММ, разделите время запятой (например, 09:00,14:00,"
                      "18:00):")
    user_states[chat_id] = 'SETTING_TIME'


def settime_reply(message):
    chat_id = message.chat.id
    times = message.text.split(',')
    update_user_data(chat_id, 'reminders', times)
    bot.reply_to(message, "Время напоминаний обновлено.")
    user_states[chat_id] = None  # Сброс состояния пользователя после выполнения


@bot.message_handler(commands=['timezone'])
def timezone_message(message):
    chat_id = message.chat.id
    safe_send_message(chat_id, "Укажите ваш часовой пояс относительно UTC (например, +3 или -5):")
    user_states[chat_id] = 'SETTING_TIMEZONE'


def timezone_reply(message):
    chat_id = message.chat.id
    try:
        time_zone = int(message.text)
        update_user_data(chat_id, 'time_zone', time_zone)
        bot.reply_to(message, "Часовой пояс обновлен.")
    except ValueError:
        bot.reply_to(message, "Пожалуйста, введите корректное числовое значение часового пояса.")
    finally:
        user_states[chat_id] = None


@bot.message_handler(commands=['goal'])
def goal_message(message):
    chat_id = message.chat.id
    safe_send_message(chat_id, "Укажите вашу цель по потреблению воды за день в литрах:")
    user_states[chat_id] = 'SETTING_GOAL'


def goal_reply(message):
    chat_id = message.chat.id
    try:
        goal = float(message.text)
        update_user_data(chat_id, 'daily_goal', goal)
        bot.reply_to(message, f"Цель по потреблению воды установлена на {goal} литров в день.")
    except ValueError:
        bot.reply_to(message, "Пожалуйста, введите числовое значение для вашей цели.")
    finally:
        user_states[chat_id] = None


@bot.message_handler(commands=['dnd'])
def dnd_message(message):
    chat_id = message.chat.id
    safe_send_message(chat_id,
                      "Укажите время для режима 'Не беспокоить' в формате ЧЧ:ММ-ЧЧ:ММ (например, 22:00-07:00). "
                      "Отправьте 'выкл', чтобы отключить режим:")
    user_states[chat_id] = 'SETTING_DND'


def dnd_reply(message):
    chat_id = message.chat.id
    if message.text.lower() == 'выкл':
        update_user_data(chat_id, 'dnd', False)
        bot.reply_to(message, "Режим 'Не беспокоить' отключен.")
    else:
        update_user_data(chat_id, 'dnd', message.text)
        bot.reply_to(message, "Время для режима 'Не беспокоить' обновлено.")
    user_states[chat_id] = None


@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    if chat_id in user_states:
        state = user_states[chat_id]

        if state == 'SETTING_TIME':
            settime_reply(message)
            user_states[chat_id] = None
        elif state == 'SETTING_TIMEZONE':
            timezone_reply(message)
            user_states[chat_id] = None
        elif state == 'SETTING_GOAL':
            goal_reply(message)
            user_states[chat_id] = None
        elif state == 'SETTING_DND':
            dnd_reply(message)
            user_states[chat_id] = None


def get_local_time_for_user(user_time_zone):
    utc_now = datetime.now(timezone.utc)
    user_local_time = utc_now + timedelta(hours=user_time_zone)
    return user_local_time


def is_within_dnd_period(user_local_time, dnd_start, dnd_end):
    start_hour, start_minute = map(int, dnd_start.split(':'))
    end_hour, end_minute = map(int, dnd_end.split(':'))
    start_time = user_local_time.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end_time = user_local_time.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)

    # Если период DND пересекает полуночь
    if end_time < start_time:
        end_time += timedelta(days=1)
        if user_local_time < start_time:
            user_local_time += timedelta(days=1)

    return start_time <= user_local_time <= end_time


def safe_send_message(chat_id, text):
    try:
        bot.send_message(chat_id, text)
    except telebot.apihelper.ApiTelegramException as e:
        if e.error_code == 403:  # Forbidden: bot was blocked by the user
            print(f"Не удалось отправить сообщение: пользователь {chat_id} заблокировал бота.")
        else:
            print(f"Ошибка при отправке сообщения пользователю {chat_id}: {e}")
    except Exception as e:
        print(f"Неожиданная ошибка при отправке сообщения пользователю {chat_id}: {e}")


def send_reminders():
    global reminder_thread_running
    while True:
        with reminder_thread_lock:
            if not reminder_thread_running:
                break
        userdata = load_user_data()
        for user_id, settings in userdata.items():
            chat_id = int(user_id)
            user_time_zone = settings.get('time_zone', 0)
            user_local_time = get_local_time_for_user(user_time_zone)
            reminders = settings.get('reminders', [])
            dnd_settings = settings.get('dnd', False)

            # Проверяем, активен ли режим "Не беспокоить"
            if dnd_settings and is_within_dnd_period(user_local_time, *dnd_settings.split('-')):
                continue  # Пропускаем напоминание, если сейчас режим DND

            user_local_time_str = user_local_time.strftime('%H:%M')
            if user_local_time_str in reminders:
                safe_send_message(chat_id, "Напоминание: выпей стакан воды!")

        time.sleep(60)  # Проверяем каждую минуту


def start_reminder_thread():
    reminder_thread = threading.Thread(target=send_reminders)
    reminder_thread.daemon = True
    reminder_thread.start()


def start_polling():
    while True:
        try:
            bot.polling(none_stop=True, timeout=2000)
        except requests.exceptions.ConnectionError:
            print("ConnectionError detected. Waiting 5 seconds before retrying...")
            time.sleep(5)
        except Exception as e:
            print(f"Unexpected error: {e}. Waiting 5 seconds before retrying...")
            time.sleep(5)


if __name__ == '__main__':
    start_reminder_thread()
    start_polling()
