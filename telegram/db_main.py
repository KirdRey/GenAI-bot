import psycopg2
from datetime import datetime
import pytz


def get_db_connection(): # Установка соединения с базой данных
     return psycopg2.connect(
            dbname="genai_kirdrey",
            user="postgres",
            password="qwerty",
            host="db",
            port="5432"
        )

def db_initialization(): # Инициализация таблиц базы данных
    conn = get_db_connection()
    create = [
        """
        CREATE TABLE IF NOT EXISTS "Chat" (
            "chat_id" serial NOT NULL UNIQUE,
            "chat_user" varchar(255) NOT NULL UNIQUE,
            PRIMARY KEY ("chat_id")
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS "messages" (
        "message_id" serial NOT NULL UNIQUE,
        "chat_id" integer NOT NULL REFERENCES "Chat"("chat_id"),
        "message_text" varchar(255) NOT NULL,
        "message_status" varchar(255) NOT NULL,
        "message_date" timestamp without time zone NOT NULL,
        "message_sender" varchar(255) NOT NULL,
        "tg_chat_id" integer NOT NULL,
        PRIMARY KEY ("message_id")
        )
        """]
    cur = conn.cursor()
    for command in create:
        cur.execute(command)   
    conn.commit()
    if conn is not None:
        conn.close()

def insert_message(data): # Добавление данных в таблицы
    chat_user = data[0]
    message_text = data[1]
    message_status = data[2]
    message_sender = data[3]
    tg_chat_id = data[4]
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
                cursor.execute("""
                INSERT INTO "chat" ("chat_user") 
                VALUES (%s)
                ON CONFLICT ("chat_user") DO NOTHING
                RETURNING "chat_id";
            """, (chat_user,))
                if cursor.rowcount == 0:
                    cursor.execute("""
                        SELECT "chat_id" FROM "chat" 
                        WHERE "chat_user" = %s;
                    """, (chat_user,))
                    chat_id = cursor.fetchone()[0]
                else:
                    chat_id = cursor.fetchone()[0]
                cursor.execute("""
                INSERT INTO "messages" 
                ("chat_id", "message_text", "message_status", "message_date", "message_sender", "tg_chat_id")
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (chat_id, message_text, message_status, datetime.now(pytz.timezone('Etc/GMT-4')), message_sender, tg_chat_id))

    except Exception as _ex:
        print("ERROR", _ex)
    finally:
        if conn:
            conn.commit()
            conn.close()
            print("Connection closed")

def get_messages(chat_id: int) -> list: # Получение списка сообщений из чата для обработки его LLM моделью
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT message_sender, message_text FROM messages 
        WHERE chat_id = %s 
        ORDER BY message_date DESC
    ''', (chat_id, ))
    messages = [{'role': row[0], 'content': row[1]} for row in cursor.fetchall()]
    messages.append({'role': 'system', 'content': "Ты бот системы поддержки и помогаешь пользователю решать его проблемы."})
    conn.close()
    return messages[::-1]

def get_chat_id_by_user(data): # Получение id чата по имени пользователя
     conn = get_db_connection()
     cursor = conn.cursor()
     cursor.execute("""
                SELECT chat_id FROM chat 
                WHERE chat_user = %s 
                LIMIT 1
            """, (data, ))
     result = cursor.fetchone()
     conn.close()
     return result

def get_last_message(data): # Получение последнего сообщения пользователя
     conn = get_db_connection()
     cursor = conn.cursor()
     cursor.execute("""
                SELECT 
                    c.chat_user,
                    m.message_text,
                    m.tg_chat_id
                FROM chat c
                JOIN messages m ON c.chat_id = m.chat_id
                WHERE c.chat_id = %s
                ORDER BY m.message_date DESC
                LIMIT 1
            """, (data,))
     result = cursor.fetchone()
     conn.close()
     return {'chat_user': result[0], 'message_text': result[1], 'tg_chat_id': result[2]}