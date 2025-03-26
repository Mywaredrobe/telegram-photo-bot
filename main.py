import sqlite3
from telebot import TeleBot, types
import time

Token = '7696737315:AAGY4roHl4TfSHONi6Wk0nbo-FbQrSDWoG8'
bot = TeleBot(Token)

temp_storage = {}
photos_to_delete = {}  # Новая переменная для удаления фото

def init_database():
    """Инициализация базы данных"""
    conn = sqlite3.connect('photo_bot.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS photos
        (file_id TEXT PRIMARY KEY,
         description TEXT,
         upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
         chat_id INTEGER)
    ''')

    conn.commit()
    conn.close()

def save_to_db(file_id, description, chat_id):
    """Сохранение фото в базу данных"""
    conn = sqlite3.connect('photo_bot.db')
    cursor = conn.cursor()

    cursor.execute('INSERT INTO photos (file_id, description, chat_id) VALUES (?, ?, ?)',
                    (file_id, description, chat_id))

    conn.commit()
    conn.close()

def search_in_db(query, chat_id):
    """Поиск фото в базе данных для конкретного пользователя"""
    conn = sqlite3.connect('photo_bot.db')
    cursor = conn.cursor()

    # Выводим информацию о поиске для отладки
    print(f"Searching for user {chat_id}: '{query}'")

    cursor.execute('SELECT file_id, description FROM photos WHERE LOWER(description) LIKE ? AND chat_id = ?',
                    (f'%{query.lower()}%', chat_id))

    results = cursor.fetchall()

    # Выводим результаты поиска для отладки
    print(f"Found {len(results)} results for user {chat_id}")
    for r in results:
        print(f"  - {r[0]}: {r[1]}")

    conn.close()

    return results

def delete_from_db(file_id, chat_id):
    """Удаление фото из базы данных по file_id и chat_id"""
    conn = sqlite3.connect('photo_bot.db')
    cursor = conn.cursor()

    cursor.execute('DELETE FROM photos WHERE file_id = ? AND chat_id = ?', (file_id, chat_id))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()

    return deleted

@bot.message_handler(commands=['start'])
def start(message):
    answer = (
        "<b>Привет!</b>\n"
        "Вы можете:\n"
        "1. Загрузить фото с описанием.\n"
        "2. Искать фото по ключевым словам.\n"
        "3. Использовать /stats для просмотра статистики.\n"
        "4. Использовать /all для просмотра всех фото.\n"
        "5. Использовать /delete для удаления фото.\n"
        "6. Использовать /clear_all для удаления всех своих фото (осторожно!).\n"
    )
    bot.send_message(message.chat.id, text=answer, parse_mode='html')

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if not message.photo:
        bot.send_message(message.chat.id, "Failed to receive the photo. Please try again.")
        return

    temp_storage[message.chat.id] = message.photo[-1].file_id
    bot.send_message(message.chat.id, "Well done. Write a description for the photo.")
    bot.register_next_step_handler(message, save_photo_description)

def save_photo_description(message):
    if not message.text:
        bot.send_message(message.chat.id, "Description must be text!")
        return

    file_id = temp_storage.get(message.chat.id)
    if not file_id:
        bot.send_message(message.chat.id, "No photo found. Please try again.")
        return

    try:
        description = message.text
        save_to_db(file_id, description, message.chat.id)
        bot.send_message(message.chat.id, "Photo and description have been saved!")
        print(f"Saved to DB: {file_id} -> {description} for user {message.chat.id}")

        del temp_storage[message.chat.id]
    except Exception as e:
        bot.send_message(message.chat.id, "An error occurred while saving the photo. Please try again.")
        print(f"Error: {e}")

@bot.message_handler(func=lambda message: not message.text.startswith('/'))
def search_photos(message):
    query = message.text.lower()
    bot.send_message(message.chat.id, f"🔍 Searching for your photos with keyword: '{query}'")

    results = search_in_db(query, message.chat.id)

    if not results:
        bot.send_message(message.chat.id, "No photos found for your query. Try another keyword.")
    else:
        bot.send_message(message.chat.id, f"Found {len(results)} photos:")
        for file_id, description in results:
            bot.send_photo(message.chat.id, file_id, caption=f"Found photo with description: {description}")

@bot.message_handler(commands=['stats'])
def show_stats(message):
    conn = sqlite3.connect('photo_bot.db')
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM photos WHERE chat_id = ?', (message.chat.id,))
    total_photos = cursor.fetchone()[0]

    cursor.execute('SELECT upload_date FROM photos WHERE chat_id = ? ORDER BY upload_date DESC LIMIT 1', (message.chat.id,))
    last_upload = cursor.fetchone()

    conn.close()

    stats = f"📊 Your statistics:\n\n" \
            f"Total photos: {total_photos}\n" \
            f"Last upload: {last_upload[0] if last_upload else 'No uploads yet'}"

    bot.send_message(message.chat.id, stats)

@bot.message_handler(commands=['all'])
def show_all(message):
    conn = sqlite3.connect('photo_bot.db')
    cursor = conn.cursor()

    cursor.execute('SELECT file_id, description FROM photos WHERE chat_id = ?', (message.chat.id,))
    results = cursor.fetchall()

    conn.close()

    if not results:
        bot.send_message(message.chat.id, "You haven't uploaded any photos yet.")
    else:
        bot.send_message(message.chat.id, f"Showing all {len(results)} your photos:")
        for file_id, description in results:
            bot.send_photo(message.chat.id, file_id, caption=description)

@bot.message_handler(commands=['delete'])
def start_delete(message):
    """Начало процесса удаления фото"""
    bot.send_message(message.chat.id, "Введите ключевое слово для поиска фотографий, которые вы хотите удалить:")
    bot.register_next_step_handler(message, show_photos_to_delete)

def show_photos_to_delete(message):
    """Показать фотографии, подходящие под критерии удаления"""
    query = message.text.lower()
    results = search_in_db(query, message.chat.id)

    if not results:
        bot.send_message(message.chat.id, "Фотографии по вашему запросу не найдены.")
        return

    # Сохраняем результаты поиска для этого пользователя
    photos_to_delete[message.chat.id] = {}

    bot.send_message(message.chat.id, f"Найдено {len(results)} фотографий. Выберите номер фотографии для удаления:")

    for i, (file_id, description) in enumerate(results, 1):
        # Сохраняем информацию о фотографии с номером
        photos_to_delete[message.chat.id][i] = file_id

        # Отправляем фотографию с номером
        bot.send_photo(
            message.chat.id,
            file_id,
            caption=f"Фото #{i}: {description}"
        )

    # Отправляем инструкцию по удалению
    bot.send_message(
        message.chat.id,
        "Введите номер фотографии, которую хотите удалить, или 'отмена' для отмены:"
    )
    bot.register_next_step_handler(message, confirm_delete)

def confirm_delete(message):
    """Подтверждение удаления выбранной фотографии"""
    if message.text.lower() == 'отмена':
        bot.send_message(message.chat.id, "Удаление отменено.")
        if message.chat.id in photos_to_delete:
            del photos_to_delete[message.chat.id]
        return

    try:
        photo_number = int(message.text)
        user_photos = photos_to_delete.get(message.chat.id, {})

        if photo_number not in user_photos:
            bot.send_message(message.chat.id, f"Фото с номером {photo_number} не найдено. Введите правильный номер или 'отмена':")
            bot.register_next_step_handler(message, confirm_delete)
            return

        file_id = user_photos[photo_number]

        # Спрашиваем подтверждение
        markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True, resize_keyboard=True)
        markup.add('Да, удалить', 'Нет, отмена')

        bot.send_message(
            message.chat.id,
            f"Вы уверены, что хотите удалить фото #{photo_number}?",
            reply_markup=markup
        )

        # Сохраняем выбранный номер для следующего шага
        photos_to_delete[message.chat.id]['selected'] = photo_number

        bot.register_next_step_handler(message, perform_delete)

    except ValueError:
        bot.send_message(message.chat.id, "Пожалуйста, введите номер фотографии цифрами или 'отмена'.")
        bot.register_next_step_handler(message, confirm_delete)

def perform_delete(message):
    """Выполнение удаления фотографии"""
    if message.text == 'Да, удалить':
        user_photos = photos_to_delete.get(message.chat.id, {})
        selected = user_photos.get('selected')

        if selected and selected in user_photos:
            file_id = user_photos[selected]

            # Удаляем фото из базы данных
            if delete_from_db(file_id, message.chat.id):
                bot.send_message(
                    message.chat.id,
                    f"Фото #{selected} успешно удалено!",
                    reply_markup=types.ReplyKeyboardRemove()
                )
            else:
                bot.send_message(
                    message.chat.id,
                    f"Ошибка при удалении фото #{selected}.",
                    reply_markup=types.ReplyKeyboardRemove()
                )
        else:
            bot.send_message(
                message.chat.id,
                "Ошибка: информация о выбранном фото не найдена.",
                reply_markup=types.ReplyKeyboardRemove()
            )
    else:
        bot.send_message(
            message.chat.id,
            "Удаление отменено.",
            reply_markup=types.ReplyKeyboardRemove()
        )

    # Очищаем информацию о фотографиях для этого пользователя
    if message.chat.id in photos_to_delete:
        del photos_to_delete[message.chat.id]

@bot.message_handler(commands=['clear_all'])
def clear_all_photos(message):
    """Очистка всех фотографий текущего пользователя из базы данных"""
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True, resize_keyboard=True)
    markup.add('Да, удалить ВСЕ МОИ', 'Нет, отмена')

    bot.send_message(
        message.chat.id,
        "⚠️ ВНИМАНИЕ! Вы действительно хотите удалить ВСЕ СВОИ фотографии? Это действие нельзя отменить!",
        reply_markup=markup
    )

    bot.register_next_step_handler(message, confirm_clear_all)

def confirm_clear_all(message):
    """Подтверждение очистки всех фотографий текущего пользователя"""
    if message.text == 'Да, удалить ВСЕ МОИ':
        conn = sqlite3.connect('photo_bot.db')
        cursor = conn.cursor()

        cursor.execute('DELETE FROM photos WHERE chat_id = ?', (message.chat.id,))
        deleted_count = cursor.rowcount

        conn.commit()
        conn.close()

        bot.send_message(
            message.chat.id,
            f"Ваша база данных фотографий очищена. Удалено {deleted_count} фотографий.",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        bot.send_message(
            message.chat.id,
            "Очистка базы данных отменена.",
            reply_markup=types.ReplyKeyboardRemove()
        )

if __name__ == "__main__":
    print("Initializing database...")
    init_database()
    print("Bot is running!")
    bot.infinity_polling()
