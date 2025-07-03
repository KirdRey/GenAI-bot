from ollama import ChatResponse
from ollama import Client
import telebot
import redis
import threading
import json
from db_main import insert_message, get_messages, get_chat_id_by_user, db_initialization, get_last_message


db_initialization() # Инициализация для создания базы данных для первого запуска
r = redis.Redis(host='redis', port=6379, db=0)

# Промпт для бота
llm_prompt = """Ты — универсальный чат-бот с гибридным интеллектом. Ты умеешь:  
- **Техподдержка** (ошибки, API, базы данных)  
- **Креативные задачи** (генерация идей, текстов, код)  
- **Консультации** (обучение, советы по инструментам)  
- **Развлечения** (игры, факты, истории)  

**Стиль общения:**  
- Технические вопросы: четко, с примерами кода/команд.  
- Креатив: эмоционально, с метафорами.  
- Общие вопросы: дружелюбно, но кратко.  

**Правила:**  
1. **Уточняй контекст**, если запрос расплывчат:  
   - *"Вы имеете в виду настройку бота или работу с API?"*  
2. **Декомпозируй сложные задачи** на шаги.  
3. **Избегай** "извините за неудобства" — заменяй на:  
   - *"Давайте разберём это вместе!"*  
4. **Предлагай вариативные решения** (простое/сложное).""" 

token = "8178035340:AAGdoHRVk4HwnbYphHd0-mwjO0LuBajh9og" # Токен Telegram бота
bot = telebot.TeleBot(token) # Иницилизация бота
client = Client(
  host='http://ollama:11434' # Инициализация LLM модели
)
client.pull('llama3:latest') # Версия модели используемой LLM 

def llm_question(chat_user: str, message: str) -> list: # Ответ LLM модели на сообщение
    messages = get_messages(get_chat_id_by_user(chat_user))
    if not messages:
        messages.append({'role': 'system', 'content': llm_prompt})

    messages.append({'role': 'user', 'content': message})

    response: ChatResponse = client.chat(model='llama3:latest', messages=messages)
    messages.append({'role': 'assistant', 'content': response.message.content})
    return messages

@bot.message_handler(commands=['start']) # Стартовое сообщение бота
def start_message(message):
    bot.send_message(message.chat.id, "Чем могу помочь?")

@bot.message_handler(content_types=['text']) # Триггер для взаимодействия с ботом
def echo_all(message):
    messages = llm_question(message.from_user.username, message.text)
    insert_message([message.from_user.username, message.text, 'sended', 'user', message.chat.id])
    insert_message([message.from_user.username, messages[-1]['content'], 'pending', 'assistant', message.chat.id])

def redis_listener(): # Отправка сообщения пользователю
    pubsub = r.pubsub()
    pubsub.subscribe("tg")
    for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"].decode("utf-8"))
            if data['action'] == 'rewrite':
                rewrite_data = get_last_message(data['chat_id'])
                messages = llm_question(rewrite_data['chat_user'], rewrite_data['message_text'])
                insert_message([rewrite_data['chat_user'], messages[-1]['content'], 'pending', 'assistant', rewrite_data['tg_chat_id']])
            elif data['action'] == 'approve':
                bot.send_message(chat_id=data['tg_chat_id'], text=data['message_text'])
threading.Thread(target=redis_listener, daemon=True).start()

bot.infinity_polling() 