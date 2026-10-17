import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import requests
from io import StringIO
import feedparser
from gigachat import GigaChat

# Настройка страницы
st.set_page_config(page_title="СППР: Сбер", layout="wide")
st.title("📊 СППР: Сбер")

# --- ФУНКЦИЯ СБОРА НОВОСТЕЙ С ФИЛЬТРАЦИЕЙ ---
def fetch_news_and_sentiment(auth_key):
    feeds = {
        "РБК": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
        "Интерфакс": "https://www.interfax.ru/rss",
    }
    
    # Ключевые слова для фильтрации релевантных новостей
    keywords = ["сбер", "банк", "цб", "ставк", "финанс", "акци", "биржа", "инвест", "деньг", "кредит"]
    
    news = []
    for source, url in feeds.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]: # Берем больше новостей (10 вместо 5)
            title_lower = entry.title.lower()
            summary_lower = entry.get("summary", "").lower()
            
            # Проверяем, есть ли ключевые слова в заголовке или тексте
            if any(kw in title_lower or kw in summary_lower for kw in keywords):
                news.append({
                    "source": source, 
                    "title": entry.title, 
                    "summary": entry.get("summary", "")[:200], 
                    "published": entry.get("published", "")
                })
    
    # Если релевантных новостей нет, отправляем хотя бы 3 для контекста
    if not news:
        for source, url in feeds.items():
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                news.append({
                    "source": source, 
                    "title": entry.title, 
                    "summary": entry.get("summary", "")[:200], 
                    "published": entry.get("published", "")
                })

    # Дальше идет оценка GigaChat
    with GigaChat(credentials=auth_key, scope="GIGACHAT_API_PERS", model="GigaChat-2", verify_ssl_certs=False) as giga:
        for item in news:
            prompt = f"""Ты — финансовый аналитик инвестиционной компании. 
Твоя задача — оценить, как эта новость повлияет на цену акций Сбербанка (SBER).
Игнорируй новости, которые не связаны с финансовым сектором, банками или экономикой России.
Верни ТОЛЬКО одно число от -1 (резко негативно) до +1 (резко позитивно).
0 — если новость нейтральна или нерелевантна.
Без лишних слов.

Заголовок: {item['title']}
Текст: {item.get('summary', '')}"""
            
            try:
                res = giga.chat(prompt)
                item['sentiment'] = float(res.choices[0].message.content.strip().replace(',', '.'))
            except:
                item['sentiment'] = 0.0
    return news

# --- ФУНКЦИЯ СКАЧИВАНИЯ КОТИРОВОК ---
def fetch_prices():
    url = "https://iss.moex.com/iss/history/engines/stock/markets/shares/boards/TQBR/securities/SBER.csv?from=2024-01-01&to=2025-12-31"
    response = requests.get(url)
    lines = response.text.split('\n')
    header_index = next(i for i, line in enumerate(lines) if "TRADEDATE" in line)
    clean_csv = '\n'.join(lines[header_index:])
    df = pd.read_csv(StringIO(clean_csv), sep='\t')
    if 'TRADEDATE' not in df.columns: 
        df = pd.read_csv(StringIO(clean_csv), sep=';')
    df = df[['TRADEDATE', 'OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']]
    df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
    df['Date'] = pd.to_datetime(df['Date'].astype(str).str.replace('.', '-', regex=False), errors='coerce')
    return df.dropna().sort_values('Date')

# --- ЗАГРУЗКА ДАННЫХ ---
try:
    AUTH_KEY = st.secrets["GIGA_AUTH_KEY"]
except:
    st.error("⚠️ Ключ GigaChat не найден в настройках Secrets. Добавь GIGA_AUTH_KEY.")
    st.stop()

# Кнопка обновления
if st.button("🔄 Обновить данные (новости и котировки)"):
    with st.spinner("Собираю свежие данные..."):
        st.session_state['news'] = fetch_news_and_sentiment(AUTH_KEY)
        st.session_state['prices'] = fetch_prices()
        st.success("Данные обновлены!")

# Если данных в сессии нет, загружаем их при первом запуске
if 'news' not in st.session_state:
    with st.spinner("Первичная загрузка данных..."):
        st.session_state['news'] = fetch_news_and_sentiment(AUTH_KEY)
        st.session_state['prices'] = fetch_prices()

news = st.session_state['news']
prices = st.session_state['prices']

last_price = prices['Close'].iloc[-1]
avg_sent = sum(n['sentiment'] for n in news) / len(news) if news else 0

# --- БЛОК МЕТРИК (РЫНОК И SENTIMENT) ---
st.subheader("📈 Текущая ситуация")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Цена (Close)", f"{last_price:.2f} ₽")
col2.metric("Средний Sentiment", f"{avg_sent:+.2f}")
col3.metric("Новостей", len(news))
col4.metric("Прогноз ETS", "~265 ₽")

# --- БЛОК ФУНДАМЕНТАЛА (АТОН) ---
st.markdown("---")
st.subheader("🏦 Фундаментальный анализ (АТОН)")

target_price = 320.0
dividend = 36.0

upside = ((target_price - last_price) / last_price) * 100

col_f1, col_f2, col_f3 = st.columns(3)
col_f1.metric("Целевая цена", f"{target_price:.2f} ₽", f"Потенциал: {upside:+.1f}%")
col_f2.metric("Дивиденды", f"{dividend:.2f} ₽")
col_f3.metric("Див. доходность", f"{(dividend/last_price)*100:.1f}%")

# --- БЛОК РЕКОМЕНДАЦИИ ---
st.markdown("---")
st.subheader("🤖 Рекомендация системы")

if avg_sent > 0.3 and last_price < target_price:
    rec_text = "🟢 **ПОКУПАТЬ**. Позитивный новостной фон и цена ниже целевой (потенциал роста)."
    rec_color = "green"
elif avg_sent < -0.3 and last_price > target_price:
    rec_text = "🔴 **ПРОДАВАТЬ**. Негативный новостной фон и цена выше целевой (риск коррекции)."
    rec_color = "red"
elif last_price < target_price and avg_sent < 0:
    rec_text = "🟡 **ЖДАТЬ**. Цена привлекательна, но новости давят. Лучше дождаться разворота sentiment."
    rec_color = "orange"
else:
    rec_text = "⚪ **ДЕРЖАТЬ**. Сильных сигналов нет. Рынок в равновесии."
    rec_color = "gray"

st.markdown(f"<h3 style='color:{rec_color};'>{rec_text}</h3>", unsafe_allow_html=True)
st.caption(f"Логика: Sentiment = {avg_sent:+.2f}, Цена = {last_price:.2f} ₽, Цель = {target_price:.2f} ₽")

st.markdown("---")

# --- ГРАФИК ---
st.subheader("📉 Динамика цены")
fig = go.Figure()
fig.add_trace(go.Scatter(x=prices['Date'], y=prices['Close'], mode='lines', name='Цена', line=dict(color='blue')))
fig.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0))
st.plotly_chart(fig, use_container_width=True)

# --- НОВОСТИ ---
st.subheader("📰 Лента новостей")
if not news:
    st.warning("Релевантных новостей за последнее время не найдено. Попробуйте обновить позже.")
else:
    for item in news:
        if item['sentiment'] > 0.2:
            color = "green"
        elif item['sentiment'] < -0.2:
            color = "red"
        else:
            color = "gray"
        st.markdown(f"**[{item['sentiment']:+.2f}]** <span style='color:{color}'>{item['title']}</span>", unsafe_allow_html=True)
        st.caption(f"_{item['source']} | {item['published']}_")

st.markdown("---")

# --- РЕШЕНИЕ ---
st.subheader("🧠 Твоё решение")
col_btn1, col_btn2, col_btn3 = st.columns(3)
col_btn1.button("🟢 Купить", use_container_width=True)
col_btn2.button("⚪ Держать", use_container_width=True)
col_btn3.button("🔴 Продать", use_container_width=True)
st.text_input("Заметка к решению:", placeholder="Почему я так решил?")
