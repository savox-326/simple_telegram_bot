import asyncio
import threading

from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from aiogram.utils import exceptions
from pytube import YouTube
from aiogram.types.input_file import InputFile
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import io
import sqlite3
from datetime import datetime
import subprocess
import multiprocessing

conn = sqlite3.connect('service.db', check_same_thread=False)
cur = conn.cursor()

BANNED = 0 # игнорируется, но логгируется
USER = 1
MODERATOR = 2
CREATOR = 3

props = [600, 200, 30, 5, 0, True, True, True, 5, True]


#max_live_msg_time = props[0]
#max_size_mb = props[1]
#max_wait_time_s = props[2]
#max_clients = props[3]
#silent_lvl = props[4]
#auto_update = props[5]
#ntf_moders_act = props[6]
#chat_for_creator = props[7]
#max_moders = props[8]
#moders_acs_lvl = props[9]


log_lvl = [BANNED, USER, MODERATOR, CREATOR]

cpu_usage = [""]

# команда для мониторинга загрузки cpu вынесена в отдельный скрипт, так как
# Popen не мог правильно интерпретировать ее
def cpu_us():
    c = subprocess.Popen("./cpu_usage.sh", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, shell=True)
    cpu_usage[0] = c.communicate()[0]
    threading.Timer(2.0, cpu_us).start()

cpu_mon = threading.Timer(2.0, cpu_us).start()

TOKEN='Здесь должен быть ваш токен на всоего бота'

# данная переменная используется для восстановления уровня доступа
CREATOR_ID = "здесь долженбыть ваш id в чате с ботом"

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

BTN_VIDEO = InlineKeyboardButton('Видео', callback_data='set_video')
BTN_AUDIO = InlineKeyboardButton('Аудио', callback_data='set_audio')
BTN_CANCEL = InlineKeyboardButton('Отмена', callback_data='set_cancel')

BTNS_ALL = [[BTN_VIDEO, BTN_AUDIO], [BTN_CANCEL]]
BTNS_VIDEO = [[BTN_VIDEO], [BTN_CANCEL]]
BTNS_AUDIO = [[BTN_AUDIO], [BTN_CANCEL]]

ALL = InlineKeyboardMarkup(inline_keyboard=BTNS_ALL)
VIDEO = InlineKeyboardMarkup(inline_keyboard=BTNS_VIDEO)
AUDIO = InlineKeyboardMarkup(inline_keyboard=BTNS_AUDIO)

BTN_ALLOW = InlineKeyboardButton('Принять', callback_data='set_allow')
BTN_DENY = InlineKeyboardButton('Отклонить', callback_data='set_deny')

BTNS_FOR_CHAT = [[BTN_ALLOW], [BTN_DENY]]
CHAT = InlineKeyboardMarkup(inline_keyboard=BTNS_FOR_CHAT)

allowed_search_types = ("num_id", "user_id", "nickname")

queue = {}

query_for_chat = {}
query_for_chat_flwr = {}
followed = {}
follower = {}

live_msg = {}

start_mes = f"Привет. Этот бот был создан в учебных целях, тут вы можете скачивать аудио или видео с YouTube. " \
            f"Есть пара ограничений: максимальное разрешение видео 720р30fps и максимальный размер видео или" \
            f"аудио составляет {props[1]} MB. Время ожидания: {props[2]} cек. В случаи если ссылка окажется " \
            f"недействительной, она будет проигнорирована. Вы также можете испльзовать " \
            f"команду /video <ссылка> или /audio <ссылка> чтобы сразу скачать медиафайл." \
            f"При обнаружении ошибок сообщите мне: @savox326"

user_commands = "Список доступных команд:\n" \
           "/start\n" \
           "/audio\n" \
           "/video\n" \
           "Чтобы узнать как пользоваться командой, введите:" \
           "\n/<команда> help или /<команда> h\n" \
           "в угловых скобках <> указаны значения, которые нужно вводить обязательно"
moderator_commands = user_commands+", в квадратных [] то, что в зависимости от команды или значения угловых скобок <>" \
                                   "вводить необязательно" \
            "\nКоманды модератора:\n" \
            "/show_load\n" \
            "/show_users\n" \
            "/start_chat\n" \
            "/stop_chat\n" \
            "/get_bio\n" \
            "/get_avatar\n" \
            "/get_user_history\n" \
            "/user_info\n" \
            "/get_chats\n" \
            "/say\n" \
            "/show_live_msg\n" \
            "/set_prop\n" \
            "/get_props\n" \
            "/set_level\n" \
            "/set_log_level\n" \
            "/get_database\n" \
            "/get_database_size\n" \
            "/stop_live_msg\n" \
            "В описании этих команд вы можете встретить такую комбинацию, как <параметр поиска> <значение>, " \
            "первое это фильтр, второе это значение с помощью которого через фильтр будет искаться пользователь\n" \
           f"доступные фильтры: {allowed_search_types}\n" \
            "Например: /user_info nickname test выведет информацию о пользователе с ником \"test\". " \
             "Также можно встретить такую комбинацию, как [live] [время], это для команд, поддерживающих " \
             "обновление данных в сообщении в реальном времени. В первом параметре обязательно нужно ввести \"live\" " \
            "чтобы система знала, что вы хотите использовать live-сообщение, второй параметр указывает на сколько " \
            f"секунд сообщение будет обновляться. Максимальное время в секундах: {props[0]}"

creator_commnads = moderator_commands+"\nКоманды владельца:\n" \
                 "/stop_chat_for\n" \
                 "/stop_live_msg_for\n" \
                 "/clean_history\n"

live_commands = ("get_props", "show_load", "show_users", "get_chats", "show_live_msg")

# Лень было возиться с исправлением логики работы функции, поэтому на скорую руку
# была описана функция-посредник для обработки исключения при вводе не цифр
def s_int(val):
    try:
        return int(val)
    except ValueError:
        return -1


def database_setup():
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
   num_id INTEGER PRIMARY KEY AUTOINCREMENT,
   user_id INTEGER,
   reg_time TEXT,
   nickname TEXT,
   full_name TEXT,
   lang TEXT,
   is_premium TEXT,
   access_lvl INTEGER,
   history INTEGER);""")
    cur.execute("""CREATE TABLE IF NOT EXISTS history(
   user_id INTEGER,
   time TEXT,
   text TEXT);""")
    conn.commit()

def get_user_info(user_id):
    val = (user_id, )
    cur.execute("SELECT * FROM users WHERE user_id = ?;", val)
    return cur.fetchone()

def get_all_users(filter=None, filter_val=None, count=False):
    symb = "COUNT(*)" if count else "*"
    if filter == None:
        cur.execute("SELECT "+symb+" FROM users;")
    elif filter == "acs_lvl":
        val = (s_int(filter_val),)
        cur.execute("SELECT "+symb+" FROM users WHERE access_lvl = ?;", val)
    elif filter == "log_lvl":
        val = (s_int(filter_val),)
        cur.execute("SELECT "+symb+" FROM users WHERE history = ?;", val)
    elif filter == "premium":
        val = (s_int(filter_val),)
        cur.execute("SELECT "+symb+" FROM users WHERE is_premium = ?;", val)
    elif filter == "date":
        val = (filter_val+"%",)
        cur.execute("SELECT "+symb+" FROM users WHERE reg_time LIKE ?;", val)
    if count:
        p = cur.fetchone()[0]
        return p
    else:
        return cur.fetchmany(50)

def get_users_id_acs_lvl(lvl):
    val = (lvl,)
    cur.execute("SELECT user_id FROM users WHERE access_lvl = ?;", val)
    return cur.fetchall()

def get_user_info_adv(val, type):
    if type == "user_id":
        return get_user_info(s_int(val))
    elif type == "num_id":
        val = (s_int(val),)
        cur.execute("SELECT * FROM users WHERE num_id = ?;", val)
        return cur.fetchone()
    elif type == "nickname":
        val = (val,)
        cur.execute("SELECT * FROM users WHERE nickname = ?;", val)
        return cur.fetchone()
    else:
        return None


def get_creators():
    val = (CREATOR, )
    cur.execute("SELECT user_id FROM users WHERE access_lvl = ?;", val)
    return cur.fetchall()

def get_moders_count():
    val = (MODERATOR, )
    cur.execute("SELECT COUNT(*) FROM users WHERE access_lvl = ?;", val)
    return cur.fetchone()[0]


async def notify_creators(text, q):
    if q[7] == MODERATOR and props[6]:
        creators = get_creators()
        answer = f"Модератор {q[4]} с id {q[1]}, с номером {q[0]} и с ником @{q[3]}" \
                 f" выполнил команду: {text}"
        if creators != None:
            for i in creators:
               await bot.send_message(i[0], answer)


def is_creator(q):
    if q[7] >= CREATOR:
        return True
    else:
        return False

def is_moderator(q):
    if q[7] >= MODERATOR and q[7] > props[4]:
        return True
    else:
        return False

def is_banned(q):
    if q[7] <= BANNED:
        return True
    else:
        return False

def is_loggable(q):
    if q[8] >= 1 and q[7] in log_lvl:
        return True
    else:
        return False


async def is_live_msg(msg: types.Message, com_name):
    text = msg.text.split()
    text_len = len(text)
    user_id = msg.from_user.id

    if text_len >= 3 and text[text_len-2] == "live" and \
           text[text_len-1].isdigit() and props[0] >= int(text[text_len-1]) > 0:
        if user_id in live_msg and com_name in live_msg[user_id]:
            await bot.send_message(msg.from_user.id, "У вас уже запущено live-сообщение для этой команды")
            return -1
        else:
            return 1
    else:
        return 0


def set_access_lvl(user_id, lvl):
    val = (lvl, user_id)
    cur.execute("UPDATE users SET access_lvl = ? WHERE user_id = ?;", val)
    conn.commit()

def set_log_lvl(user_id, lvl):
    val = (lvl, user_id)
    cur.execute("UPDATE users SET history = ? WHERE user_id = ?;", val)
    conn.commit()

async def chatting(user_id, text, command=True):
    dt = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    val = (user_id, dt, text)
    if user_id in follower and not command:
        await bot.send_message(follower[user_id], text)
        val = (user_id, dt, f"to {follower[user_id]} -> " + text)
        cur.execute("INSERT INTO history VALUES(?, ?, ?);", val)
        val = (follower[user_id], dt, f"from {user_id} -> " + text)
        cur.execute("INSERT INTO history VALUES(?, ?, ?);", val)
        conn.commit()
    elif user_id in followed:
        await bot.send_message(followed[user_id], text)
        val = (user_id, dt, f"to {followed[user_id]} -> " + text)
        cur.execute("INSERT INTO history VALUES(?, ?, ?);", val)
        val = (followed[user_id], dt, f"from {user_id} -> " + text)
        cur.execute("INSERT INTO history VALUES(?, ?, ?);", val)
        conn.commit()


def set_prop(prop, value):
    if prop == "silent_lvl":
        props[4] = value
    elif prop == "auto_data_update":
        props[5] = bool(value)
    elif prop == "ntf_moders_acts":
        props[6] = bool(value)
    elif prop == "chat_for_creator":
        props[7] = bool(value)
    elif prop == "max_moders":
        props[8] = value
    elif prop == "moders_acs_lvl":
        props[9] = bool(value)
    elif prop == "max_media_size":
        if value > 1000:
            props[1] = 1000
        else:
            props[1] = value
    elif prop == "max_clients":
        if value > 10:
            props[3] = 10
        else:
            props[3] = value
    elif prop == "max_wait_time":
        if value > props[0]:
            props[2] = props[0]
        else:
            props[2] = value


def _user_check(msg: types.Message):
    user_data = msg.from_user
    q = get_user_info(msg.from_user.id)
    dt = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    if q==None:
        val = (user_data.id, dt, user_data.username, user_data.full_name, user_data.language_code,
               str(user_data.is_premium), USER, 1)
        cur.execute("INSERT INTO users VALUES(null, ?, ?, ?, ?, ?, ?, ?, ?);", val)
        conn.commit()

        q = get_user_info(msg.from_user.id)

    if is_loggable(q):
        val = (user_data.id, dt, msg.text)
        cur.execute("INSERT INTO history VALUES(?, ?, ?);", val)
        conn.commit()

    if props[5]:
        update_user_data(q, msg)
    return q


def get_user_history(user_id, date=None, count=False):
    symb = "COUNT(*)" if count else "*"
    if date == None:
        val = (user_id, )
        cur.execute("SELECT " + symb + " FROM history WHERE user_id = ?;", val)
    else:
        val = (user_id, date + "%",)
        cur.execute("SELECT " + symb + " FROM history WHERE user_id = ? and time LIKE ?;", val)
    if count:
        p = cur.fetchone()[0]
        return p
    else:
        return cur.fetchmany(50)



def rm_user_history(user_id, date=None):
    if date == None:
        val = (user_id, )
        cur.execute("DELETE FROM history WHERE user_id = ?;", val)
    else:
        val = (user_id, date + "%",)
        cur.execute("DELETE FROM history WHERE user_id = ? and time LIKE ?;", val)
    conn.commit()


def rm_all_history(date=None):
    if date == None:
        cur.execute("DELETE FROM history;")
    else:
        val = (date + "%",)
        cur.execute("DELETE FROM history WHERE user_id = ? and time LIKE ?;", val)
    conn.commit()


def delete_live_msg(user_id, command):
    if user_id in live_msg:
        if command in live_msg[user_id]:
            live_msg[user_id].remove(command)
            if len(live_msg[user_id]) == 0:
                del live_msg[user_id]
            return True
    return False

async def live_message(user_id, command, time, op):
    i = 0
    time = int(time)
    t_msg = await bot.send_message(user_id, "Запуск live-сообщения")

    text = ""
    last_text = ""

    reject = "\n\nlive-сообщено было отключено"
    timeout = "\n\nвремя действия live-сообщения истекло"

    if not user_id in live_msg:
        live_msg[user_id] = []

    live_msg[user_id].append(command)
    while True:
        if i > time:
            delete_live_msg(user_id, command)
            await bot.edit_message_text(op() + timeout, user_id, t_msg.message_id)
            return
        if not user_id in live_msg or \
            not command in live_msg[user_id]:
            delete_live_msg(user_id, command)
            await bot.edit_message_text(op() + reject, user_id, t_msg.message_id)
            return
        text = op()
        text += "\n\nlive-сообщение"
        try:
            await bot.edit_message_text(text, user_id, t_msg.message_id)
        except exceptions.MessageNotModified:
            pass
        except:
            p = delete_live_msg(user_id, command)
        i += 2
        await asyncio.sleep(2)



def user_check(msg: types.Message):
    q = _user_check(msg)
    return not is_banned(q)

def update_user_data(q, msg: types.Message):
    user_data = msg.from_user
    changes = False
    if q[3] != user_data.username:
        changes = True
        val = (user_data.username, user_data.id)
        cur.execute("UPDATE users SET username = ? WHERE user_id = ?;", val)
    if q[4] != user_data.full_name:
        changes = True
        val = (user_data.full_name, user_data.id)
        cur.execute("UPDATE users SET full_name = ? WHERE user_id = ?;", val)
    if q[5] != user_data.language_code:
        changes = True
        val = (user_data.language_code, user_data.id)
        cur.execute("UPDATE users SET lang = ? WHERE user_id = ?;", val)
    if q[6] != user_data.is_premium:
        changes = True
        val = (str(user_data.is_premium), user_data.id)
        cur.execute("UPDATE users SET is_premium = ? WHERE user_id = ?;", val)
    if changes:
        conn.commit()


def queue_setter(id, type):
    if id in queue:
        queue[id] = type


async def is_service_available(msg: types.Message, ref_to_vid):
    q = _user_check(msg)
    if props[4] >= q[7]:
        return False
    elif msg.from_user.id in queue:
        #await bot.delete_message(msg.from_user.id, msg.message_id)
        return False
    elif len(queue) > props[3]:
        await bot.send_message(msg.from_user.id, "Сервис перегружен, повторите попытку позже")
        return False
    try:
        yt = YouTube(ref_to_vid)
        return True
    except:
        return False


async def command_syntax_check(msg: types.Message, help, par, should_check):
    if len(par) == 2 and (par[1] == "help" or par[1] == "h"):
        await bot.send_message(msg.from_user.id, help)
        return False

    else:
        if not should_check():
            await bot.send_message(msg.from_user.id, "Неверный синтаксис команды")
            await bot.send_message(msg.from_user.id, help)
            return False
        else:
            return True

# Должно было быть query_for_chat но поздно заметил и исправлять везде
# имя этой функции было лень
async def query_for_char(flwr, flwd):
    i = 0

    q = get_user_info(flwr)

    flwd_text = f"Пользователь {q[4]} с id {q[1]}, с номером {q[0]} и с ником @{q[3]}" \
           f" хочет начать чат с вами"

    flwr_text = "Запрос отправлен"
    timeout = "Время ожидания истекло. Запрос отклонен"
    reject = "Запрос отклонен"
    allow = "Запрос принят. Чат с пользователем начат"

    flwd_msg = await bot.send_message(flwd, flwd_text, reply_markup=CHAT)
    flwr_msg = await bot.send_message(flwr, flwr_text)

    query_for_chat[flwd] = "none"
    query_for_chat_flwr[flwr] = flwd

    while True:
        if i > props[2]:
            del query_for_chat[flwd]
            del query_for_chat_flwr[flwr]
            try:
                await bot.edit_message_text(timeout, flwr, flwr_msg.message_id)
                await bot.edit_message_text(flwd_text+"\n\n"+timeout, flwd, flwd_msg.message_id, reply_markup=None)
                return
            except exceptions:
                query_for_chat[flwd] = "deny"
        if query_for_chat[flwd] == "deny":
            del query_for_chat[flwd]
            del query_for_chat_flwr[flwr]
            await bot.edit_message_text(reject, flwr, flwr_msg.message_id)
            await bot.edit_message_text(flwd_text+"\n\n"+reject, flwd, flwd_msg.message_id, reply_markup=None)
            return
        if not query_for_chat[flwd] == "none":
            break
        i+=1
        await asyncio.sleep(1)

    del query_for_chat[flwd]
    del query_for_chat_flwr[flwr]
    await bot.edit_message_text(allow, flwr, flwr_msg.message_id)
    await bot.edit_message_text(flwd_text + "\n\n" + allow, flwd, flwd_msg.message_id, reply_markup=None)

    followed[flwd] = flwr
    follower[flwr] = flwd

# Я не знаю почему но именно эта часть кода по максимиму загружает cpu на небольшой промежуток
# времени. Поэтому, чтобы программа не блокировалась было решено обернуть эту часть
# в функцию-посредника для выполнения в асинхронной среде (asyncio.get_event_loop().run_in_executor)
def exec_prepare(output: multiprocessing, ref_to_vid):
    yt = YouTube(ref_to_vid)
    output.put(yt.streams)

async def execute_query(ref_to_vid, msg: types.Message):
    i = 0

    queue[msg.from_user.id] = "none"

    msg_last = await bot.send_message(msg.from_user.id, "Получаем данные")
    msg_id = msg_last.message_id

    q = multiprocessing.Manager().Queue()
    yt = YouTube(ref_to_vid)
    await asyncio.get_event_loop().run_in_executor(None, exec_prepare, q, ref_to_vid)
    streams = q.get()

    video_best = streams.filter(progressive=True).get_highest_resolution()
    audio_best = streams.filter(only_audio=True).desc().first()

    video_size = video_best.filesize_mb
    audio_size = audio_best.filesize_mb

    final_text = f"Размер видео составит: {video_size} MB\nРазмер аудио составит: {audio_size} MB"

    if video_size < props[1] and audio_size > props[1]:
        final_text = final_text+"\nРазмер аудио превышает допустимый, скачивание недоступно"
        await bot.edit_message_text(final_text, msg.from_user.id, msg_id, reply_markup=VIDEO)

    elif video_size > props[1] and audio_size < props[1]:
        final_text = final_text+"\nРазмер видео превышает допустимый, скачивание недоступно"
        await bot.edit_message_text(final_text, msg.from_user.id, msg_id, reply_markup=AUDIO)

    elif video_size > props[1] and audio_size > props[1]:
        del queue[msg.from_user.id]
        final_text = final_text+"\nРазмер видео и аудио превышает допустимый, скачивание недоступно"
        await bot.edit_message_text(final_text, msg.from_user.id, msg_id)
        return

    else:
        await bot.edit_message_text(final_text, msg.from_user.id, msg_id, reply_markup=ALL)

    while True:
        if not queue[msg.from_user.id] == "none":
            break
        if i > props[2]:
            del queue[msg.from_user.id]
            final_text+="\n\nВремя ожидания истекло. Запрос отклонен"
            await bot.edit_message_text(final_text, msg.from_user.id, msg_id, reply_markup=None)
            return
        i+=1
        await asyncio.sleep(1)

    f = io.BytesIO()
    if queue[msg.from_user.id] == "cancel":
        del queue[msg.from_user.id]
        final_text += "\n\nЗапрос отклонен"
        await bot.edit_message_text(final_text, msg.from_user.id, msg_id, reply_markup=None)
    elif queue[msg.from_user.id] == "audio" and not (audio_size > props[1]):
        final_text1 = final_text+"\n\nПриступаем к скачиванию"
        await bot.edit_message_text(final_text1, msg.from_user.id, msg_id, reply_markup=None)
        msg_id = msg_last.message_id
        await asyncio.get_event_loop().run_in_executor(None, audio_best.stream_to_buffer, f)
        f.seek(0)
        final_text1 = final_text + "\n\nОтправляем"
        await bot.edit_message_text(final_text1, msg.from_user.id, msg_id)
        await bot.send_audio(msg.from_user.id, InputFile(f, "audio.mp3"))
        del queue[msg.from_user.id]
        final_text1 = final_text + "\n\nОтправлено"
        await bot.edit_message_text(final_text1, msg.from_user.id, msg_id)
    elif queue[msg.from_user.id] == "video" and not (video_size > props[1]):
        final_text1 = final_text + "\n\nПриступаем к скачиванию"
        await bot.edit_message_text(final_text1, msg.from_user.id, msg_id, reply_markup=None)
        await asyncio.get_event_loop().run_in_executor(None, video_best.stream_to_buffer, f)
        f.seek(0)
        final_text1 = final_text + "\n\nОтправляем"
        await bot.edit_message_text(final_text1, msg.from_user.id, msg_id)
        await bot.send_video(msg.from_user.id, InputFile(f, "video.mp4"))
        del queue[msg.from_user.id]
        final_text1 = final_text + "\n\nОтправлено"
        await bot.edit_message_text(final_text1, msg.from_user.id, msg_id)
    else:
        del queue[msg.from_user.id]
        final_text1 = final_text + "\n\nНекорректный запрос"
        await bot.edit_message_text(final_text1, msg.from_user.id, msg_id, reply_markup=None)


async def execute_query_lite(ref_to_vid, msg: types.Message, type):
    queue[msg.from_user.id] = "none"
    msg_last = await bot.send_message(msg.from_user.id, "Получаем данные")
    msg_id = msg_last.message_id

    q = multiprocessing.Manager().Queue()
    yt = YouTube(ref_to_vid)
    await asyncio.get_event_loop().run_in_executor(None, exec_prepare, q, ref_to_vid)
    streams = q.get()

    video_best = streams.filter(progressive=True).get_highest_resolution()
    audio_best = streams.filter(only_audio=True).desc().first()

    video_size = video_best.filesize_mb
    audio_size = audio_best.filesize_mb

    await bot.edit_message_text("Приступаем к скачиванию", msg.from_user.id, msg_id)

    f = io.BytesIO()
    if type == "audio" and not (audio_size > props[1]):
        await asyncio.get_event_loop().run_in_executor(None, audio_best.stream_to_buffer, f)
        f.seek(0)
        await bot.edit_message_text("Отправляем", msg.from_user.id, msg_id)
        await bot.send_audio(msg.from_user.id, InputFile(f, "audio.mp3"))
        del queue[msg.from_user.id]
        await bot.delete_message(msg.from_user.id, msg_id)
    elif type == "video" and not (video_size > props[1]):
        await asyncio.get_event_loop().run_in_executor(None, video_best.stream_to_buffer, f)
        f.seek(0)
        await bot.edit_message_text("Отправляем", msg.from_user.id, msg_id)
        await bot.send_video(msg.from_user.id, InputFile(f, "video.mp4"))
        del queue[msg.from_user.id]
        await bot.delete_message(msg_id, msg.from_user.id)
    elif audio_size > props[1] and type == "audio":
        del queue[msg.from_user.id]
        await bot.send_message(msg.from_user.id, "Размер аудио превышает допустимый, скачивание недоступно")
    elif video_size > props[1] and type == "video":
        del queue[msg.from_user.id]
        await bot.send_message(msg.from_user.id, "Размер видео превышает допустимый, скачивание недоступно")
    else:
        del queue[msg.from_user.id]
        await bot.send_message(msg.from_user.id, "Некорректное значение. Запрос отклонен")
    return

@dp.message_handler(commands=['start'])
async def process_start(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    if not user_check(msg):
        return

    await bot.send_message(msg.from_user.id, start_mes)

@dp.message_handler(commands=['commands'])
async def process_commands(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if is_banned(q):
        return

    final = creator_commnads if is_creator(q) else moderator_commands if is_moderator(q) else user_commands
    await bot.send_message(msg.from_user.id, final)

GET_AVATAR = "/get_avatar <параметр поиска> <значение> [номер аватарки] -- скачать аватарку пользователя. " \
             "all в качестве параметра \"номер аватарки\" скачает все аватарки. Если не указать последний " \
             "параметр, будет сообщено о количество аватарок"
@dp.message_handler(commands=['get_avatar'])
async def process_get_avatar(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()
    text_len = len(text)

    op = lambda: ((text_len == 4 and (text[3]=="all" or text[3].isdigit())) or
                    text_len == 3) and text[1] in allowed_search_types

    if not await command_syntax_check(msg, GET_AVATAR, text, op):
        return

    t_user = get_user_info_adv(text[2], text[1])

    if t_user == None:
        await bot.send_message(msg.from_user.id, "Пользователь не найден")
        return

    num_digit = False
    if text_len == 4:
        num = text[3]
        if num.isdigit():
            num_digit = True
            num = int(text[3])-1
    else:
        num = "?"

    pict = await bot.get_user_profile_photos(t_user[1])
    pict_count = pict.total_count
    if pict_count == 0:
        await bot.send_message(msg.from_user.id, "У пользователя нет аватарок")
        await notify_creators(msg.text, q)
    elif num_digit and (num > pict_count or num < 0):
        await bot.send_message(msg.from_user.id, "Неверный номер аватарки")
    elif num == "all":
        for i in range(pict_count):
            await msg.answer_photo(dict((pict.photos[i][0])).get("file_id"))
        await notify_creators(msg.text, q)
    elif num == "?":
        await bot.send_message(msg.from_user.id, f"Количество аватарок: {pict_count}")
        await notify_creators(msg.text, q)
    elif num_digit:
        await msg.answer_photo(dict((pict.photos[num][0])).get("file_id"))
        await notify_creators(msg.text, q)


GET_BIO = "/get_bio <параметр поиска> <значение> -- получить биографию (статус) пользователя"
@dp.message_handler(commands=['get_bio'])
async def process_get_bio(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()

    op = lambda: len(text) == 3 and text[1] in allowed_search_types

    if not await command_syntax_check(msg, GET_BIO, text, op):
        return

    t_user = get_user_info_adv(text[2], text[1])

    if t_user == None:
        await bot.send_message(msg.from_user.id, "Пользователь не найден")
        return

    user = await bot.get_chat(t_user[1])
    user_bio = user.bio

    if user_bio == None:
        await bot.send_message(msg.from_user.id, f"У пользователя нет Био")
    else:
        await bot.send_message(msg.from_user.id, f"Био пользователя:\n{user_bio}")
    await notify_creators(msg.text, q)


SHOW_USERS = "/show_users [параметр поиска] [значение] [live] [время] -- получить список всех пользователей. " \
             "параметры поиска: acs_lvl - поиск по уровню доступа,\nlog_lvl - поиск по уровню логгирования,\n" \
             "premium - поиск пользователей с премиумом или без"
@dp.message_handler(commands=['show_users'])
async def process_show_users(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()
    text_len = len(text)

    allwd_pars = ("acs_lvl", "log_lvl", "premium", "date")

    op = lambda: text_len == 1 or ((text_len==3 or text_len==5) and (text[1] in allwd_pars or text[1]=="live"))

    if not await command_syntax_check(msg, SHOW_USERS, text, op):
        return

    if text_len > 1:
        if text[1] in allwd_pars:
            res_len = lambda: get_all_users(text[1], text[2], True)
            op1 = lambda: get_all_users(text[1], text[2])
        else:
            res_len = lambda: get_all_users(count=True)
            op1 = lambda: get_all_users()
    else:
        res_len = lambda: get_all_users(count=True)
        op1 = lambda:  get_all_users()

    def show_users():
        if res_len==0:
            final = "Нет результатов"
        else:
            op = f"\n\nВсего найдено: {res_len()}"
            final = "\n\n".join(str(x) for x in op1())+op
        return final

    op_f = lambda: show_users()

    l = await is_live_msg(msg, "show_users")

    if l == 1:
        await notify_creators(msg.text, q)
        await live_message(msg.from_user.id, "show_users", text[-1], op_f)
    elif l == -1:
        return
    else:
        await bot.send_message(msg.from_user.id, op_f())
        await notify_creators(msg.text, q)


START_CHAT = "/start_chat <параметр поиска> <значение> [уведом.] -- начать чат с пользователем от лица бота. " \
             "Пользователь не будет видеть вводимые вами команды, однако вы будете видеть его команды. " \
             "параметр \"уведом.\" используется если вы хотите отправить запрос или скрыто начать чат:\n" \
             "0 - скрыто\n1 - послать запрос\nДля других модераторов или владельца запрос отправляется всегда"
@dp.message_handler(commands=['start_chat'])
async def process_start_chat(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()
    text_len = len(text)

    op = lambda: text_len == 3 or (text_len == 4 and text[3].isdigit() and 0 <= int(text[3]) <= 1) and \
                 text[1] in allowed_search_types

    if not await command_syntax_check(msg, START_CHAT, text, op):
        return
    t_user = get_user_info_adv(text[2], text[1])

    if t_user == None:
        await bot.send_message(msg.from_user.id, "Пользователь не найден")
        return

    #if is_banned(t_user):
    #   await bot.send_message(msg.from_user.id, "Вы не можете начать чат с заблокированным пользователем")

    elif t_user[1] == q[1]:
        await bot.send_message(msg.from_user.id, "Нельзя начать чат с самим собой")

    elif q[1] in query_for_chat_flwr:
        q = get_user_info(query_for_chat_flwr[q[1]])
        await bot.send_message(msg.from_user.id, f"Вы уже отправили запрос на чат с пользователем. "
                                                 f"Пользователь {q[4]} с id {q[1]}, с номером {q[0]} и с ником @{q[3]}")

    elif t_user[1] in followed:
        q = get_user_info(followed[t_user[1]])
        await bot.send_message(msg.from_user.id, f"Этот пользоваель уже состоит в чате с модератором. "
                                                 f"Модератор {q[4]} с id {q[1]}, с номером {q[0]} и с ником @{q[3]}")
    elif msg.from_user.id in follower:
        q = get_user_info(follower[msg.from_user.id])
        await bot.send_message(msg.from_user.id, f"Вы уже состоите в чате с пользователем. "
                                                 f"Пользователь {q[4]} с id {q[1]}, с номером {q[0]} и с ником @{q[3]}")

    elif msg.from_user.id in followed:
        q = get_user_info(followed[msg.from_user.id])
        await bot.send_message(msg.from_user.id, f"Вы уже состоите в чате с пользователем. "
                                                 f"Пользователь {q[4]} с id {q[1]}, с номером {q[0]} и с ником @{q[3]}")

    elif is_creator(t_user) and props[7]:
        await bot.send_message(msg.from_user.id, "В данный момент нельзя начать чат с владельцем")

    elif not is_creator(q) and (is_moderator(t_user) or is_creator(t_user)) or \
            (text_len == 4 and text[3].isdigit() and int(text[3]) == 1):
        await query_for_char(q[1], t_user[1])
        await notify_creators(msg.text, q)

    else:
        followed[t_user[1]] = q[1]
        follower[q[1]] = t_user[1]
        await bot.send_message(msg.from_user.id, "Чат с пользователем начат")
        await notify_creators(msg.text, q)


STOP_CHAT = "/stop_chat -- остановить чат с пользователем"
@dp.message_handler(commands=['stop_chat'])
async def process_stop_chat(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()

    op = lambda: len(text) == 1

    if not await command_syntax_check(msg, STOP_CHAT, text, op):
        return


    if q[1] in follower:
        t_user = get_user_info(follower[q[1]])
        del follower[q[1]]
        del followed[t_user[1]]
    elif q[1] in followed:
        t_user = get_user_info(followed[q[1]])
        del followed[q[1]]
        del follower[t_user[1]]
    else:
        await bot.send_message(msg.from_user.id, "Вы ни с кем не состоите в чате")
        return

    await bot.send_message(msg.from_user.id, f"Чат с пользователем прекращен. "
                                             f"Пользователь {t_user[4]} с id {t_user[1]}, с номером {t_user[0]} и с ником @{t_user[3]}")
    await notify_creators(msg.text, q)



GET_DATABASE = "/get_database -- отправить базу данных"
@dp.message_handler(commands=['get_database'])
async def process_get_database(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()

    op = lambda: len(text) == 1

    if not await command_syntax_check(msg, GET_DATABASE, text, op):
        return

    await bot.send_document(msg.from_user.id, open('service.db', 'rb'))
    await notify_creators(msg.text, q)



GET_DATABASE_SIZE = "/get_database_size -- вернуть размер базы данных"
@dp.message_handler(commands=['get_database_size'])
async def process_get_database(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()

    op = lambda: len(text) == 1

    if not await command_syntax_check(msg, GET_DATABASE_SIZE, text, op):
        return

    q1 = multiprocessing.Manager().Queue()

    def get_size(res: multiprocessing):
        out = subprocess.Popen("du -sh service.db", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, shell=True).communicate()[0]
        out = out.split()[0]
        last = out[-1]
        out = out[:-1]
        if last == "G":
            out += " ГБ"
        elif last == "M":
            out += " МБ"
        elif last == "K":
            out += " КБ"
        res.put(out)

    await asyncio.get_event_loop().run_in_executor(None, get_size, q1)

    await bot.send_message(msg.from_user.id, f"Размер базы данных составляет: {q1.get()}")
    await notify_creators(msg.text, q)



SAY = "/say <сообщение> -- разослать информационное сообщение всем пользователям"
@dp.message_handler(commands=['say'])
async def process_say(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split(maxsplit=1)
    op = lambda: len(text) == 2

    if not await command_syntax_check(msg, SAY, text, op):
        return

    users = get_users_id_acs_lvl(USER)
    if users != None:
        for i in users:
            await bot.send_message(i[0], text[1])

    who = "Владелец" if is_creator(q) else "Модератор"
    temp = who+f" {q[4]} с id {q[1]}, с номером {q[0]} и с ником @{q[3]}" \
                 f" отправил глобальное сообщение: {text[1]}"
    moders = get_users_id_acs_lvl(MODERATOR)
    if moders != None:
        for i in moders:
            await bot.send_message(i[0], temp)
    await bot.send_message(msg.from_user.id, "Сообщение отправлено")
    await notify_creators(text, q)



GET_USER_HISTORY = "/get_user_history <параметр поиска> <значение> [дата] -- получить историю запросов пользователя. " \
                   "дата - получить историю за указанную дату"
@dp.message_handler(commands=['get_user_history'])
async def process_get_user_history(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()
    op = lambda: 4 >= len(text) >= 3

    if not await command_syntax_check(msg, GET_USER_HISTORY, text, op):
        return

    t_user = get_user_info_adv(text[2], text[1])

    if t_user == None:
        await bot.send_message(msg.from_user.id, "Пользователь не найден")
        return

    if len(text) == 4:
        res_len = get_user_history(t_user[1], text[3], True)
        op1 = get_user_history(t_user[1], text[3])
    else:
        res_len = get_user_history(t_user[1], count=True)
        op1 = get_user_history(t_user[1])

    if res_len==0:
        op_2 = lambda: "Нет результатов"
    else:
        op_1 = f"\n\nВсего сообщений: {res_len}"
        op_2 = lambda: "\n\n".join(str(x) for x in op1)+op_1

    await bot.send_message(msg.from_user.id, op_2())
    await notify_creators(msg.text, q)




USER_INFO = "/user_info <параметр поиска> <значение> -- просмотреть информацию о пользователе"
@dp.message_handler(commands=['user_info'])
async def process_user_info(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    user = _user_check(msg)
    if not is_moderator(user):
        return

    text = msg.text.split()

    op = lambda: len(text) == 3 and text[1] in allowed_search_types

    if not await command_syntax_check(msg, USER_INFO, text, op):
        return
    q = get_user_info_adv(text[2], text[1])

    if q == None:
        await bot.send_message(msg.from_user.id, "Пользователь не найден")
        return

    def get_info():
        answer = f"num_id: {q[0]}\nuser_id: {q[1]}\nдата регистрации: {q[2]}\nnickname: @{q[3]}\n" \
             f"имя: {q[4]}\nязык: {q[5]}\nпремиум: {q[6]}\nуровень доступа: {q[7]}\nвведение логов: {q[8]}"
        return answer

    op = lambda: get_info()

    await bot.send_message(msg.from_user.id,op())
    await notify_creators(msg.text, user)



SET_LEVEL = "/set_level <параметр поиска> <значение> [уровень] -- установить уровень доступа для пользователя." \
            " уровень доступа должен быть от 0 до 2, если его не указать будет показан текущий уровень доступа\n" \
            "0 - Забанен; 1 - Пользователь; 2 - Модератор; 3 - Владелец"
@dp.message_handler(commands=['set_level'])
async def process_set_level(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()

    op = lambda: len(text) == 3 or\
                 (len(text) == 4 and (text[3].isdigit() and 0 <= int(text[3]) < 3)) and \
                 text[1] in allowed_search_types

    if not await command_syntax_check(msg, SET_LEVEL, text, op):
        return
    t_user = get_user_info_adv(text[2], text[1])

    if len(text) == 3:
        await bot.send_message(msg.from_user.id, f"Уровень логгирования пользователя: {t_user[7]}")
        await notify_creators(msg.text, q)

    else:
        lvl = int(text[3])
        if not is_creator(q) and is_creator(t_user):
            await bot.send_message(msg.from_user.id, "Вы не можете изменить уровень доступа для владельца")
        elif t_user[7] == lvl:
            await bot.send_message(msg.from_user.id, "Пользователь уже имеет такой уровень доступа")
        elif is_moderator(q) and not props[9] and lvl > MODERATOR or (is_moderator(t_user) and lvl < MODERATOR):
            await bot.send_message(msg.from_user.id, "Сейчас нельзя изменять уроаень доступа на модератора"
                                                     "или для них")
        elif get_moders_count() >= props[8] and lvl > USER:
            await bot.send_message(msg.from_user.id, "Достигнут предел количества модераторов")
        else:
            await bot.send_message(msg.from_user.id, "Уровень доступа изменен")
            set_access_lvl(t_user[1], lvl)
            await notify_creators(msg.text, q)



SET_PROP = "/set_prop <параметр> [доп.] <значение>  -- изменить базовые параметры сервиса." \
           " параметры: max_clients -- макс. количество польз., которые могут одновременно скачивать медиа,\n" \
           "max_wait_time -- макс. время ожидания в сек. для польз.,\n" \
           "max_media_size -- макс. допустимый размер для скачивания медиа в МБ,\n" \
           "silent_lvl -- уровень игнорирования:\n0 - только забаненные,\n" \
           "1 - пользователи в том числе,\n2 - модераторы в том числе\n" \
           "auto_data_update -- авто обновление изменившихся данных пользователя:" \
           "\n0 - отключено,\n1 - включено"
@dp.message_handler(commands=['set_prop'])
async def process_set_prop(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()

    allowed_props = ("max_wait_time", "max_media_size", "silent_lvl", "auto_data_update")
    allwd_opt_props = ("rm", "add")
    allwd_prop_creator = ("ntf_moders_acts", "log_lvl", "chat_for_creator", "max_moders", "moders_acs_lvl")


    adv = "\nntf_moders_acts - сообщать владельцам вводимые модераторами команды\n" \
          "log_lvl -- общий уровень логгирования:\n0 - только забаненные,\n" \
          "1 - только пользователи,\n2 - только модераторы,\n3 - только владелец\n" \
          "доп. для этой команды: add - добавить, rm - удалить\n" \
          "chat_for_creator - могут ли модераторы начать чат с владельцем\n" \
          "max_moders - максимально разрешенное количество модераторов\n" \
          "moders_acs_lvl - могут ли модераторы менять уровень доступа для других" \
          "модераторов и назначать модераторами других пользователей"
    final = SET_PROP + adv if is_creator(q) else SET_PROP

    op = lambda: (is_creator(q) and len(text) == 4 and (text[2] in allwd_opt_props)) or \
                  len(text) == 3 and \
                 (text[1] in allowed_props or (is_creator(q) and text[1] in allwd_prop_creator)) and \
                  text[len(text)-1].isdigit()

    if not await command_syntax_check(msg, final, text, op):
        return

    lvl = int(text[2])

    if lvl < 0:
        await bot.send_message(msg.from_user.id, "Уровень параметра не может быть меньше нуля")
    elif (text[1] == "silent_lvl" and lvl >= 0 and q[7] <= lvl):
        await bot.send_message(msg.from_user.id, "Вы не можете выставить уровень игнорирования больше "
                                                 "или равным вашему уровню доступа")
    elif text[1] == "silent_lvl" and lvl >= 0 and q[7] >= lvl:
        await bot.send_message(msg.from_user.id, "Параметр изменен")
        set_prop(text[1], lvl)
        await notify_creators(msg.text, q)
    elif text[1] == "auto_data_update" or \
         text[1] == "chat_for_creator" or \
         text[1] == "ntf_moders_acts" or \
         text[1] == "moders_acs_lvl":
        if 1 >= lvl:
            set_prop(text[1], lvl)
            await bot.send_message(msg.from_user.id, "Параметр изменен")
            await notify_creators(msg.text, q)
        else:
            await bot.send_message(msg.from_user.id, "Неверное значение")
    elif text[1] == "log_lvl":
        if lvl > CREATOR:
            await bot.send_message(msg.from_user.id, "Неверное значение")
        else:
            if text[2] == "rm":
                log_lvl.remove(lvl)
            else:
                log_lvl.append(lvl)
            await bot.send_message(msg.from_user.id, "Параметр изменен")
            await notify_creators(msg.text, q)
    else:
        set_prop(text[1], lvl)
        await bot.send_message(msg.from_user.id, "Параметр изменен")
        await notify_creators(msg.text, q)



GET_PROPS = "/get_props [live] [время] -- получить базовые параметры сервиса." \
           " параметры: max_clients -- макс. количество польз., которые могут одновременно скачивать медиа,\n" \
           "max_wait_time -- макс. время ожидания в сек. для польз.,\n" \
           "max_media_size -- макс. допустимый размер для скачивания медиа в МБ,\n" \
           "silent_lvl -- уровень игнорирования:\n0 - только забаненные,\n" \
           "1 - пользователи в том числе,\n2 - модераторы в том числе\n" \
           "auto_data_update -- авто обновление изменившихся данных пользователя:" \
           "\n0 - отключено,\n1 - включено\n" \
           "max_moders - максимально разрешенное количество модераторов"
@dp.message_handler(commands=['get_props'])
async def process_get_props(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()

    op = lambda: len(text) == 1 or len(text) == 3

    adv = "\nntf_moders_acts - сообщать владельцам вводимые модераторами команды\n" \
          "доп. для этой команды: add - добавить, rm - удалить\n" \
          "log_lvl -- общий уровень логгирования:\n0 - только забаненные,\n" \
          "1 - только пользователи,\n2 - только модераторы,\n3 - только владелец\n" \
          "chat_for_creator - могут ли модераторы начать чат с владельцем\n" \
          "moders_acs_lvl - могут ли модераторы менять уровень доступа для других" \
          "модераторов и назначать модераторами других пользователей"
    final = GET_PROPS+adv if is_creator(q) else GET_PROPS

    if not await command_syntax_check(msg, final, text, op):
        return

    def get_props():
        answer = f"max_wait_time: {props[2]}\nmax_media_size: {props[1]}\n" \
             f"silent_lvl: {props[4]}\nauto_data_update: {int(props[5])}\n" \
                 f"max_moders: {props[8]}"
        if is_creator(q):
            answer += f"\nntf_moders_acts: {int(props[6])}\nlog_lvl: {log_lvl}\n" \
                  f"chat_for_creator: {int(props[7])}\nmoders_acs_lvl: {int(props[9])}"
        return answer

    op = lambda: get_props()

    l = await is_live_msg(msg, "get_props")
    if l == 1:
        await notify_creators(msg.text, q)
        await live_message(msg.from_user.id, "get_props", text[-1], op)
    elif l == -1:
        return
    else:
        await bot.send_message(msg.from_user.id, op())
        await notify_creators(msg.text, q)


SHOW_LOAD = "/show_load [live] [время] -- показать очередь, загрузку ОЗУ и процессора"
@dp.message_handler(commands=['show_load'])
async def process_show_load(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()

    op = lambda: len(text) == 1 or len(text) == 3

    if not await command_syntax_check(msg, SHOW_LOAD, text, op):
        return

    def get_load():
        #Mem:
        buf = subprocess.Popen("free --mega | grep Mem:", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, shell=True).communicate()[0]
        buf = buf.split()

        buf1 = subprocess.Popen("df -T -h | grep ext4", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, shell=True).communicate()[0]
        buf1 = buf1.split()

        res = "Очередь на скачивание:\n" \
             f"{queue}\n\n" \
              f"Постоянная память\n" \
              f"всего: {buf1[2]} ГБ\n" \
              f"использовано:  {buf1[3]} ГБ\n" \
              f"доступно:  {buf1[4]} ГБ\n\n" \
              "Оперативная память\n" \
             f"всего:  {buf[1]} MБ\n" \
             f"использовано:  {buf[2]} MБ\n" \
             f"буф./врем. : {buf[5]} МБ\n" \
             f"доступно:  {buf[6]} MБ\n\n" \
             f"загрузка CPU: {cpu_usage[0]}%"
        return res

    op = lambda: get_load()

    l = await is_live_msg(msg, "show_load")
    if l == 1:
        await notify_creators(msg.text, q)
        await live_message(msg.from_user.id, "show_load", text[-1], op)
    elif l == -1:
        return
    else:
        await bot.send_message(msg.from_user.id, op())
        await notify_creators(msg.text, q)


SET_LOG_LEVEL = "/set_log_level <параметр поиска> <значение> [уровень] -- включить/выключить введение истории" \
                " запросов (логгирование) для пользователя. если не указать последний параиетр, будет показан" \
                "текущий уровень. Уровень логгирования должен быть либо 0, либо 1\n" \
                "0 - Выключен; 1 - Включен"
@dp.message_handler(commands=['set_log_level'])
async def process_set_log_level(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()

    op = lambda: (len(text) == 4 and text[3].isdigit() and 0 <= int(text[3]) <= 1) or \
                 len(text) == 3 and \
                 text[1] in allowed_search_types


    if not await command_syntax_check(msg, SET_LOG_LEVEL, text, op):
        return
    t_user = get_user_info_adv(text[2], text[1])

    if t_user == None:
        await bot.send_message(msg.from_user.id, "Пользователь не найден")
        return

    if len(text) == 3:
        await bot.send_message(msg.from_user.id, f"Уровень логгирования пользователя: {t_user[8]}")
        await notify_creators(msg.text, q)

    else:
        lvl = int(text[3])
        if is_creator(t_user):
            await bot.send_message(msg.from_user.id, "Вы не можете изменить уровень логгирования для владельца")
        elif t_user[7] == lvl:
            await bot.send_message(msg.from_user.id, "Пользователь уже имеет такой уровень логгирования")
        else:
            await bot.send_message(msg.from_user.id, "Уровень логгирования изменен")
            set_log_lvl(t_user[1], lvl)
            await notify_creators(msg.text, q)



RESET_ACCESS = "/reset_access -- восстановить права доступа владельца"
@dp.message_handler(commands=['reset_access'])
async def process_reset_access(msg: types.Message):
    q = _user_check(msg)

    if q[1] == int(CREATOR_ID):
        set_access_lvl(q[1], 3)
        set_log_lvl(q[1], 0)
        await bot.send_message(msg.from_user.id, "Права владельца восстановлены")


GET_CHATS = "/get_chats [live] [время] -- Показать активные чаты"
@dp.message_handler(commands=['get_chats'])
async def process_get_chats(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()

    op = lambda: len(text) == 3 or len(text) == 1

    if not await command_syntax_check(msg, GET_CHATS, text, op):
        return

    res = f"Активные чаты:\n{follower}\n\n" \
          f"Ожидают подтверждения:\n{query_for_chat_flwr}"
    op = lambda: res

    l = await is_live_msg(msg, "get_chats")

    if l == 1:
        await live_message(msg.from_user.id, "get_chats", text[-1], op)
        await notify_creators(msg.text, q)
    elif l == -1:
        return
    else:
        await bot.send_message(msg.from_user.id, op())
        await notify_creators(msg.text, q)



SHOW_LIVE_MSG = "/show_live_msg [live] [время] -- Показать активные live-сообщения"
@dp.message_handler(commands=['show_live_msg'])
async def process_show_live_msg(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()

    op = lambda: len(text) == 3 or len(text) == 1

    if not await command_syntax_check(msg, SHOW_LIVE_MSG, text, op):
        return

    op = lambda: f"live-сообщения:\n{live_msg}"

    l = await is_live_msg(msg, "show_live_msg")

    if l == 1:
        await live_message(msg.from_user.id, "show_live_msg", text[-1], op)
        await notify_creators(msg.text, q)
    elif l == -1:
        return
    else:
        await bot.send_message(msg.from_user.id, op())
        await notify_creators(msg.text, q)



STOP_LIVE_MSG = "/stop_live_msg <параметр> -- остановить live-сообщение. " \
                "параметр - название команды, на котором нужно остановить live-сообщение, " \
                "all остановит все live-сообщения"
@dp.message_handler(commands=['stop_live_msg'])
async def process_stop_live_msg(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_moderator(q):
        return

    text = msg.text.split()

    op = lambda: len(text) == 2 and (text[1] in live_commands or text[1] == "all")
    if not await command_syntax_check(msg, STOP_LIVE_MSG, text, op):
        return

    if not msg.from_user.id in live_msg:
        await bot.send_message(msg.from_user.id, "У вас нет live-cообщений")
        return

    if text[1] == "all":
        for i in live_commands:
            delete_live_msg(msg.from_user.id, i)
        await bot.send_message(msg.from_user.id, "live-cообщения остановлены")
        await notify_creators(msg.text, q)
    else:
        if delete_live_msg(msg.from_user.id, text[1]):
            await bot.send_message(msg.from_user.id, "live-cообщение остановлено")
            await notify_creators(msg.text, q)
        else:
            await bot.send_message(msg.from_user.id, "У вас нет такого live-cообщения")



STOP_LIVE_MSG_FOR = "/stop_live_msg_for <параметр или поиск> <значение> <параметр> -- остановить live-сообщение для пользователя. " \
                    "параметр - название команды, на котором нужно остановить live-сообщение, " \
                    "all остановит все live-сообщения"
@dp.message_handler(commands=['stop_live_msg_for'])
async def process_stop_live_msg_for(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_creator(q):
        return

    text = msg.text.split()
    text_len = len(text)

    op = lambda: (text_len == 2 and (text[1] in live_commands or text[1] == "all")) or\
                 (text_len == 4 and (text[3] in live_commands or text[3] == "all"))
    if not await command_syntax_check(msg, STOP_LIVE_MSG_FOR, text, op):
        return

    t_user = get_user_info_adv(text[2], text[1])

    if t_user == None:
        await bot.send_message(msg.from_user.id, "Пользователя не найден")
        return

    res = False

    if not t_user[1] in live_msg:
        await bot.send_message(msg.from_user.id, "У пользователя нет live-cообщений")
        return
    elif len(live_msg) == 0:
        await bot.send_message(msg.from_user.id, "Нет запущенных live-cообщений")
        return

    if text[1] == "all":
        for i in live_msg:
            if delete_live_msg(msg.from_user.id, i):
                res = True
        if res:
            await bot.send_message(t_user[1], "live-cообщения остановлены")
            return
    elif text_len == 2:
        for i in live_msg:
            for j in live_msg[text[2]]:
                if delete_live_msg(t_user[2], text[1]):
                    await bot.send_message(msg.from_user.id, "live-cообщения остановлены")
                    return
        await bot.send_message(msg.from_user.id, "Такое live-cообщение не было запущено")
        return
    elif text_len == 4 and text[3] == "all":
        for j in live_msg[text[2]]:
            delete_live_msg(t_user[2], text[1])
        await bot.send_message(msg.from_user.id, "live-cообщения остановлены")



CLEAN_HISTORY = "/clean_history <параметр или поиск> <значение> [дата] -- очистить историю запросов всю, за определенную " \
                "дату или для пользователя, all удалит всю историю"
@dp.message_handler(commands=['clean_history'])
async def process_clean_history(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    q = _user_check(msg)
    if not is_creator(q):
        return

    text = msg.text.split()
    text_len = len(text)

    op = lambda: text_len == 2 or (4 >= text_len >= 3 and (text[1] in allowed_search_types))
    if not await command_syntax_check(msg, CLEAN_HISTORY, text, op):
        return

    if text_len >= 3:
        t_user = get_user_info_adv(text[2], text[1])
        if text_len == 4:
            rm_user_history(t_user[1], text[3])
        else:
            rm_user_history(t_user[1])
    elif text_len == 2:
        if text[1] == "all":
            rm_all_history()
        else:
            rm_all_history(text[1])
    await bot.send_message(msg.from_user.id, "Выполнено")


VIDEO_HELP = "/video <ссылка> -- скачать видео из youtube"
@dp.message_handler(commands=['video'])
async def process_video(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    if not user_check(msg):
        return

    text = msg.text.split()

    op = lambda: len(text) == 2

    if await command_syntax_check(msg, VIDEO_HELP, text, op) and await is_service_available(msg, text[1]):
        await execute_query_lite(msg.text, msg, "video")


AUDIO_HELP = "/audio <ссылка> -- скачать аудио из youtube-видео"
@dp.message_handler(commands=['audio'])
async def process_audio(msg: types.Message):
    await chatting(msg.from_user.id, msg.text)
    if not user_check(msg):
        return

    text = msg.text.split()

    op = lambda: len(text) == 2

    if await command_syntax_check(msg, AUDIO_HELP, text, op) and await is_service_available(msg, text[1]):
        await execute_query_lite(msg.text, msg, "audio")


@dp.message_handler(content_types=['text'])
async def handle_text(msg: types.Message):
    await chatting(msg.from_user.id, msg.text, False)
    if not user_check(msg):
        return

    text = msg.text

    allowed = "https://youtu.be"
    ref = text[:len(allowed)]

    if ref == allowed and await is_service_available(msg, text):
        await execute_query(text, msg)

@dp.callback_query_handler(text="set_video")
async def send_random_value(call: types.CallbackQuery):
    queue_setter(call.from_user.id, "video")

@dp.callback_query_handler(text="set_audio")
async def send_random_value(call: types.CallbackQuery):
    queue_setter(call.from_user.id, "audio")

@dp.callback_query_handler(text="set_cancel")
async def send_random_value(call: types.CallbackQuery):
    queue_setter(call.from_user.id, "cancel")

@dp.callback_query_handler(text="set_deny")
async def send_random_value(call: types.CallbackQuery):
    if call.from_user.id in query_for_chat:
        query_for_chat[call.from_user.id] = "deny"

@dp.callback_query_handler(text="set_allow")
async def send_random_value(call: types.CallbackQuery):
    if call.from_user.id in query_for_chat:
        query_for_chat[call.from_user.id] = "allow"

if __name__ == '__main__':
    database_setup()
    executor.start_polling(dp)

