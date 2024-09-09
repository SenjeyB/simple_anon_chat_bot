import telebot
from telebot import types
import sqlite3
from datetime import datetime

API_TOKEN = 'FIND IT YOURSELF'
bot = telebot.TeleBot(API_TOKEN)
ADMIN_ID = 0

users = {}
conversations = {}
genders = {}
search = {}

conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        gender TEXT,
        target_gender TEXT,
        state TEXT
    )
''')
cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id INTEGER PRIMARY KEY, 
                    subscribed INTEGER DEFAULT 1
               )
               ''')
cursor.execute('''CREATE TABLE IF NOT EXISTS ignored_users (
                    user_id INTEGER PRIMARY KEY)''')
conn.commit()

def save_user(user_id, gender, target_gender):
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, gender, target_gender, state)
        VALUES (?, ?, ?, ?)
    ''', (user_id, gender, target_gender, 'ready'))
    conn.commit()

def is_ignored(user_id):
    cursor.execute('SELECT 1 FROM ignored_users WHERE user_id = ?', (user_id,))
    return cursor.fetchone() is not None

def get_user(user_id):
    cursor.execute('SELECT * FROM users WHERE user_id=?', (user_id,))
    return cursor.fetchone()

def update_user_state(user_id, state):
    cursor.execute('UPDATE users SET state=? WHERE user_id=?', (state, user_id))
    conn.commit()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    cursor.execute('INSERT OR IGNORE INTO subscriptions (user_id) VALUES (?)', (message.chat.id,))
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, row_width=1)
    markup.add('Мужчина', 'Женщина', 'Другое')
    msg = bot.send_message(message.chat.id, "Выберите ваш пол:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_gender_step)

@bot.message_handler(commands=['settings'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, row_width=1)
    markup.add('Мужчина', 'Женщина', 'Другое')
    msg = bot.send_message(message.chat.id, "Выберите ваш пол:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_gender_step)

def process_gender_step(message):
    gender = message.text
    if gender in ['Мужчина', 'Женщина', 'Другое']:
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, row_width=1)
        markup.add('Мужчина', 'Женщина', 'Другое', 'Любой')
        msg = bot.send_message(message.chat.id, "Кого вы хотите найти?", reply_markup=markup)
        bot.register_next_step_handler(msg, process_search_step, gender)
    else:
        msg = bot.send_message(message.chat.id, "Пожалуйста, выберите правильный пол.")
        bot.register_next_step_handler(msg, process_gender_step)

def process_search_step(message, gender):
    target_gender = message.text
    if target_gender in ['Мужчина', 'Женщина', 'Другое', 'Любой']:
        save_user(message.chat.id, gender, target_gender)
        bot.send_message(message.chat.id, "Настройки сохранены! Используйте команду /find для поиска собеседника.")
    else:
        msg = bot.send_message(message.chat.id, "Пожалуйста, выберите правильный вариант.")
        bot.register_next_step_handler(msg, process_search_step, gender)

@bot.message_handler(commands=['find'])
def find_companion(message):
    user = get_user(message.chat.id)
    if user:
        user_id = user[0]
        update_user_state(user_id, 'searching')
        bot.send_message(user_id, "Ищем собеседника... Для отмены поиска используйте команду /cancel.")
        cursor.execute('''
            SELECT user_id FROM users
            WHERE state="searching" AND user_id!=? AND
            (target_gender=? OR target_gender="Любой")
        ''', (user_id, user[1]))
        
        companion = cursor.fetchone()
        if companion:
            companion_id = companion[0]
            update_user_state(user_id, 'in_conversation')
            update_user_state(companion_id, 'in_conversation')
            conversations[user_id] = companion_id
            conversations[companion_id] = user_id
            bot.send_message(user_id, "Собеседник найден! Вы можете начать общение.")
            bot.send_message(companion_id, "Собеседник найден! Вы можете начать общение.")
        else:
            bot.send_message(user_id, "В поиске по данному фильтру пока никого нет. Ожидайте начало диалога.")
    else:
        bot.send_message(message.chat.id, "Пожалуйста, сначала настройте ваш профиль с помощью /settings.")

@bot.message_handler(commands=['stop'])
def stop_conversation(message):
    user_id = message.chat.id
    end_conversation(user_id)
    bot.send_message(user_id, "Диалог завершен. Используйте /find для поиска нового собеседника.")

@bot.message_handler(commands=['next'])
def next_conversation(message):
    user_id = message.chat.id
    end_conversation(user_id)
    find_companion(message)

@bot.message_handler(commands=['cancel'])
def cancel_search(message):
    user_id = message.chat.id
    user = get_user(user_id)
    if user and user[3] == 'searching':
        update_user_state(user_id, 'ready')
        bot.send_message(user_id, "Поиск собеседника остановлен.")
    else:
        bot.send_message(user_id, "Вы не находитесь в процессе поиска.")

@bot.message_handler(commands=['updatehistory'])
def subscribe_again(message):
    user_id = message.chat.id
    cursor.execute('REPLACE INTO subscriptions (user_id, subscribed) VALUES (?, 1)', (user_id,))
    conn.commit()

    bot.send_message(user_id, 'Вы успешно подписались на обновления.')

@bot.message_handler(commands=['update'])
def send_update(message):
    user_id = message.chat.id
    if user_id != ADMIN_ID:
        bot.send_message(user_id, '<b>Ошибка:</b> команда недоступна.', parse_mode='HTML')
        return

    update_text = message.text[len('/update'):].strip()

    if update_text == "":
        bot.send_message(user_id, '<b>Ошибка:</b> укажите текст обновления.', parse_mode='HTML')
        return

    cursor.execute('SELECT user_id FROM subscriptions WHERE subscribed = 1')
    subscribed_users = cursor.fetchall()

    for user in subscribed_users:
        try:
            markup = types.InlineKeyboardMarkup()
            unsubscribe_button = types.InlineKeyboardButton("Отписаться", callback_data=f'unsubscribe_{user[0]}')
            markup.add(unsubscribe_button)
            
            bot.send_message(user[0], update_text, parse_mode='HTML', reply_markup=markup)
        except Exception as e:
            print(f"Ошибка при отправке сообщения пользователю {user[0]}: {e}")

    bot.send_message(user_id, 'Обновление успешно отправлено.')

@bot.message_handler(commands=['bug'])
def report_bug(message):
    user_id = message.chat.id
    bug_report = message.text[len('/bug'):].strip()

    if bug_report == "":
        bot.send_message(user_id, '<b>Ошибка:</b> опишите проблему после команды /bug.', parse_mode='HTML')
        return

    formatted_report = f'<b>Новый баг-репорт</b>\n\n' \
                       f'<b>От пользователя:</b> <code>{user_id}</code>\n' \
                       f'<b>Сообщение:</b>\n{bug_report}\n\n' \
                       f'<b>Дата:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'

    markup = types.InlineKeyboardMarkup()
    ignore_button = types.InlineKeyboardButton("Игнорировать", callback_data=f'ignore_{user_id}')
    markup.add(ignore_button)

    if not is_ignored(user_id):
        bot.send_message(ADMIN_ID, formatted_report, parse_mode='HTML', reply_markup=markup)
    bot.send_message(user_id, 'Спасибо за сообщение! Ваш баг-репорт был отправлен администратору.')

def end_conversation(user_id):
    if user_id in conversations:
        companion_id = conversations.pop(user_id)
        if companion_id in conversations:
            conversations.pop(companion_id)
            bot.send_message(companion_id, "Собеседник покинул чат.")
        update_user_state(user_id, 'ready')
        update_user_state(companion_id, 'ready')

def send_message(user_id, content_type, file_id=None, caption=None):
    if user_id in conversations:
        target_user_id = conversations[user_id]
        try:
            if content_type == 'text':
                bot.send_message(target_user_id, caption)
            elif content_type == 'sticker':    
                bot.send_sticker(target_user_id, file_id)
            elif content_type == 'voice':
                bot.send_voice(target_user_id, file_id)
            elif content_type == 'video_note':
                bot.send_video_note(target_user_id, file_id)
            elif content_type == 'video':
                bot.send_video(target_user_id, file_id, caption=caption)
            elif content_type == 'photo':
                bot.send_photo(target_user_id, file_id, caption=caption)
            elif content_type == 'document':
                bot.send_document(target_user_id, file_id, caption=caption)
            elif content_type == 'animation':
                bot.send_animation(target_user_id, file_id, caption=caption)
        except:
            bot.send_message(user_id, "Сообщение не доставлено. Диалог завершен.")
            end_conversation(user_id)
    else:
        bot.send_message(user_id, "Вы не в диалоге. /find чтобы найти.")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.chat.id
    text = message.text
    send_message(user_id, 'text', caption=text)

@bot.message_handler(content_types=['sticker'])
def handle_sticker(message):
    user_id = message.chat.id
    sticker_id = message.sticker.file_id
    send_message(user_id, 'sticker', file_id=sticker_id)

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    user_id = message.chat.id
    voice_id = message.voice.file_id
    caption = message.caption if message.caption else None
    send_message(user_id, 'voice', file_id=voice_id, caption=caption)

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.chat.id
    photo_id = message.photo[-1].file_id
    caption = message.caption if message.caption else None
    send_message(user_id, 'photo', file_id=photo_id, caption=caption)
    

@bot.message_handler(content_types=['video'])
def handle_video(message):
    user_id = message.chat.id
    video_id = message.video.file_id
    caption = message.caption if message.caption else None
    send_message(user_id, 'video', file_id=video_id, caption=caption)

@bot.message_handler(content_types=['video_note'])
def handle_video_note(message):
    user_id = message.chat.id
    video_note_id = message.video_note.file_id
    send_message(user_id, 'video_note', file_id=video_note_id)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.chat.id
    document_id = message.document.file_id
    caption = message.caption if message.caption else None
    send_message(user_id, 'document', file_id=document_id, caption=caption)

@bot.message_handler(content_types=['animation'])
def handle_animation(message):
    user_id = message.chat.id
    animation_id = message.animation.file_id
    caption = message.caption if message.caption else None
    send_message(user_id, 'animation', file_id=animation_id, caption=caption)

@bot.callback_query_handler(func=lambda call: call.data.startswith('unsubscribe_'))
def handle_unsubscribe(call):
    user_id = int(call.data.split('_')[1])
    cancel(call.message)
    cursor.execute('UPDATE subscriptions SET subscribed = 0 WHERE user_id = ?', (user_id,))
    conn.commit()

    bot.send_message(user_id, 'Вы отписались от обновлений.')
    bot.send_message(user_id, '/updatehistory чтобы подписаться обратно.')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ignore_'))
def handle_ignore(call):
    user_id = int(call.data.split('_')[1])
    cursor.execute('INSERT OR IGNORE INTO ignored_users (user_id) VALUES (?)', (user_id,))
    conn.commit()

    bot.send_message(call.message.chat.id, f'Пользователь {user_id} был добавлен в список игнорируемых.')
    bot.answer_callback_query(call.id, text="Пользователь игнорируется.")

bot.polling()