import streamlit as st
import psycopg2
from datetime import datetime
import json
import redis
from streamlit_autorefresh import st_autorefresh

# Стиль web-интерфейса
STYLE = """
<style>
    :root {
        --primary-color: #0084ff;
        --secondary-color: #f0f2f5;
        --user-msg-color: #0084ff;
        --assistant-msg-color: #e4e6eb;
        --pending-msg-color: #fff3bf;
        --text-color: #050505;
        --light-text: #65676b;
        --border-radius: 18px;
    }

    .stApp {
        background-color: #878787;
    }

    .sidebar .sidebar-content {
        background: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }

    /* Стиль сообщений пользователя */
    .user-message {
        background-color: var(--user-msg-color);
        color: white;
        padding: 12px 16px;
        margin: 8px 0;
        border-radius: var(--border-radius) var(--border-radius) 0 var(--border-radius);
        max-width: 70%;
        margin-left: auto;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }

    /* Стиль сообщений ассистента */
    .assistant-message {
        background-color: var(--assistant-msg-color);
        color: var(--text-color);
        padding: 12px 16px;
        margin: 8px 0;
        border-radius: var(--border-radius) var(--border-radius) var(--border-radius) 0;
        max-width: 70%;
        margin-right: auto;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }

    /* Стиль ожидающих модерации сообщений */
    .pending-message {
        background-color: var(--pending-msg-color);
        border-left: 4px solid #ffc107;
    }

    /* Кнопки */
    .stButton>button {
        background-color: var(--primary-color);
        color: white;
        border-radius: var(--border-radius);
        border: none;
        padding: 8px 16px;
        font-weight: 500;
        transition: all 0.2s;
    }

    .stButton>button:hover {
        background-color: #0069d9;
        color: white;
        transform: translateY(-1px);
    }

    /* Заголовки */
    h1, h2, h3 {
        color: var(--text-color);
    }

    /* Панель модерации */
    .moderation-panel {
        background: white;
        padding: 16px;
        border-radius: var(--border-radius);
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        margin-top: 20px;
    }

    /* Время сообщения */
    .message-time {
        font-size: 0.75rem;
        color: var(--light-text);
        margin-top: 4px;
    }
</style>
"""

count = st_autorefresh(interval=10 * 1000, limit=None, key="refresh") # Автообновление интерфейса каждые 10 секунд
def get_db_connection(): # Подключение к базе данных
    return psycopg2.connect(
        dbname="genai_kirdrey",
        user="postgres",
        password="qwerty",
        host="db",
        port="5432"
    )

def get_chats(): # Получение списка чатов для визуализации
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    c.chat_id,
                    c.chat_user,
                    (SELECT MAX(message_date) FROM messages WHERE chat_id = c.chat_id) as last_message,
                    COUNT(CASE WHEN m.message_status = 'pending' THEN 1 END) as pending_count
                FROM chat c
                LEFT JOIN messages m ON c.chat_id = m.chat_id
                GROUP BY c.chat_id
                ORDER BY last_message DESC NULLS LAST
            """)
            return cur.fetchall()
    finally:
        conn.close()

def get_chat_messages(chat_id): # Получение содержимого чатов для визуализации
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    message_id,
                    message_text, 
                    message_sender, 
                    message_date, 
                    message_status,
                    tg_chat_id
                FROM messages
                WHERE chat_id = %s
                ORDER BY message_date
            """, (chat_id,))
            return cur.fetchall()
    finally:
        conn.close()

def update_message(message_id, new_text, action, chat_id, tg_chat_id): # Редактура информации присланной LLM-моделью
    conn = get_db_connection()
    r = redis.Redis(host='redis', port=6379, db=0)
    try:
        with conn.cursor() as cur:
            if action == "approve":
                cur.execute("""
                    UPDATE messages
                    SET message_status = 'sended'
                    WHERE message_id = %s
                    RETURNING message_text
                """, (message_id,))
                approved_text = cur.fetchone()[0]
                r.publish("tg", json.dumps({
                    'chat_id': chat_id,
                    'tg_chat_id': tg_chat_id,
                    'action': 'approve',
                    'message_text': approved_text
                }))
            
            elif action == "approve_edited":
                cur.execute("""
                    UPDATE messages
                    SET message_text = %s, message_status = 'sended'
                    WHERE message_id = %s
                """, (new_text, message_id))
                r.publish("tg", json.dumps({
                    'chat_id': chat_id,
                    'tg_chat_id': tg_chat_id,
                    'action': 'approve',
                    'message_text': new_text
                }))
            
            elif action == "reject":
                cur.execute("""
                    DELETE FROM messages
                    WHERE message_id = %s
                """, (message_id,))
                r.publish("tg", json.dumps({
                    'chat_id': chat_id,
                    'tg_chat_id': tg_chat_id,
                    'action': 'rewrite'
                }))
            
            conn.commit()
    finally:
        conn.close()

def main(): # Основная часть функции, в которой инициализируется сам web-интерфейс
    st.set_page_config(layout="wide", page_title="Модератор чатов", page_icon="💬")
    st.markdown(STYLE, unsafe_allow_html=True)
    
    if 'selected_chat' not in st.session_state:
        st.session_state.selected_chat = None
    if 'pending_index' not in st.session_state:
        st.session_state.pending_index = 0
    
    chats = get_chats()
    
    with st.sidebar:
        st.header("💬 Чаты")
        st.markdown("---")
        
        for chat_id, chat_user, last_message, pending_count in chats:
            col1, col2 = st.columns([4, 1])
            
            with col1:
                if st.button(chat_user, key=f"chat_btn_{chat_id}", use_container_width=True):
                    st.session_state.selected_chat = chat_id
                    st.session_state.pending_index = 0
                    st.rerun()
            
            with col2:
                if pending_count > 0:
                    st.markdown(
                        f"""
                        <div style="
                            background-color: #ff4b4b;
                            color: white;
                            border-radius: 10px;
                            padding: 2px 6px;
                            font-size: 0.8em;
                            text-align: center;
                            margin-top: 8px;
                        ">
                            {pending_count}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
    
    if st.session_state.selected_chat:
        chat_id = st.session_state.selected_chat
        messages = get_chat_messages(chat_id)
        
        pending_messages = [msg for msg in messages if msg[4] == 'pending']
        
        st.header(f"Чат с пользователем")
        
        chat_container = st.container()
        with chat_container:
            for msg in messages:
                msg_id, text, sender, date, status, _ = msg
                time_str = date.strftime('%H:%M')
                
                if sender == 'user':
                    st.markdown(
                        f"""
                        <div class='user-message'>
                            {text}
                            <div class='message-time'>{time_str}</div>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
                else:
                    message_class = "assistant-message pending-message" if status == 'pending' else "assistant-message"
                    st.markdown(
                        f"""
                        <div class='{message_class}'>
                            {text}
                            <div class='message-time'>{time_str}</div>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
        
        if pending_messages:
            current_msg = pending_messages[st.session_state.pending_index]
            msg_id, text, _, _, _, tg_chat_id = current_msg
            
            with st.container():
                st.markdown("---")
                st.markdown(f"**Модерация сообщения {st.session_state.pending_index + 1}/{len(pending_messages)}**")
                
                with st.expander("Редактировать сообщение", expanded=True):
                    edited_text = st.text_area("Текст:", value=text, height=150, label_visibility="collapsed")
                    
                    cols = st.columns(4)
                    with cols[0]:
                        if st.button("✅ Одобрить", type="primary"):
                            update_message(msg_id, text, "approve", chat_id, tg_chat_id)
                            st.success("Сообщение одобрено!")
                            st.rerun()
                    with cols[1]:
                        if st.button("✏️ С правками"):
                            update_message(msg_id, edited_text, "approve_edited", chat_id, tg_chat_id)
                            st.success("Сообщение обновлено!")
                            st.rerun()
                    with cols[2]:
                        if st.button("❌ Отклонить"):
                            update_message(msg_id, None, "reject", chat_id, tg_chat_id)
                            st.success("Сообщение отклонено!")
                            st.rerun()
                    with cols[3]:
                        if len(pending_messages) > 1:
                            if st.button("⏭️ Следующее"):
                                st.session_state.pending_index = (st.session_state.pending_index + 1) % len(pending_messages)
                                st.rerun()
        else:
            st.success("🎉 Нет сообщений, ожидающих модерации")
    else:
        st.info("👈 Выберите чат из списка слева")

if __name__ == "__main__":
    main()