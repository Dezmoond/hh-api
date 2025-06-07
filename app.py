from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import json
import re
import sqlite3

app = Flask(__name__, template_folder="startbootstrap-clean-blog-gh-pages/templates",
            static_folder="startbootstrap-clean-blog-gh-pages/static")

# Список площадок для парсинга
VENUES = [
    {"id": "filarmoniya", "name": "Филармония", "url": "https://quicktickets.ru/chita-filarmoniya"},
    {"id": "uzory", "name": "Забайкальские узоры", "url": "https://quicktickets.ru/chita-zabajkalskie-uzory"},
    {"id": "rodina", "name": "КЗ Родина", "url": "https://quicktickets.ru/chita-kz-rodina"},
    {"id": "teatr", "name": "Театр Забайкалья", "url": "https://quicktickets.ru/chita-teatr-zabajkale"},
    {"id": "oficerov", "name": "Дом офицеров", "url": "https://quicktickets.ru/chita-dom-oficerov"}
]

RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
}

DATABASE = 'events.db'


def init_db():
    """Инициализирует базу данных SQLite."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                date TEXT NOT NULL,         -- Storing original date string (e.g., "15 мая 19:00")
                ticket_link TEXT,
                image_url TEXT,
                venue_name TEXT NOT NULL,
                original_venue_id TEXT NOT NULL,
                parsed_datetime TEXT,       -- New column to store sortable datetime (ISO format: YYYY-MM-DDTHH:MM:SS)
                unique_key TEXT UNIQUE      -- Ensures no duplicate events
            )
        ''')
        conn.commit()


def parse_date_string_to_datetime(date_str):
    """
    Парсит русскую строку даты "День Месяц Время" в объект datetime.
    При отсутствии года, пытается определить его, чтобы дата была как можно ближе к текущей.
    """
    try:
        day_str, month_name, time_str = date_str.split()
        day = int(day_str)
        month = RU_MONTHS[month_name.lower()]
        hour, minute = map(int, time_str.split(':'))

        current_year = datetime.now().year

        # Попробуем текущий год
        try:
            event_dt = datetime(current_year, month, day, hour, minute)
        except ValueError:  # Если день/месяц невалидны для текущего года (например, 29 февраля в невисокосном году)
            # Если текущий год не подходит, попробуем следующий. Это для случаев типа "29 февраля" в невисокосном году
            # или если дата уже прошла в этом году, а значит, она могла быть в прошлом.
            event_dt = datetime(current_year + 1, month, day, hour, minute)

            # Корректировка года, чтобы дата была ближайшей к текущей дате
        # Если дата в будущем более чем на 6 месяцев, скорее всего это прошлый год
        if event_dt > datetime.now() and (event_dt - datetime.now()).days > 180:
            event_dt = event_dt.replace(year=event_dt.year - 1)
        # Если дата в прошлом более чем на 6 месяцев, скорее всего это следующий год
        elif event_dt < datetime.now() and (datetime.now() - event_dt).days > 180:
            event_dt = event_dt.replace(year=event_dt.year + 1)

        return event_dt
    except Exception as e:
        print(f"Не удалось распарсить дату '{date_str}': {e}")
        return None


def add_event_to_db(event):
    """Добавляет мероприятие в базу данных, избегая дубликатов."""
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        # Используем только первую дату для записи в БД и создания unique_key
        if not event['dates']:
            print(f"Событие '{event['title']}' не имеет даты. Пропускаем добавление в БД.")
            return

        first_date_str = event['dates'][0]

        # Парсим дату в объект datetime для сортировки и создания unique_key
        parsed_dt = parse_date_string_to_datetime(first_date_str)
        if not parsed_dt:
            print(f"Не удалось распарсить дату для события '{event['title']}'. Пропускаем добавление в БД.")
            return

        # Уникальный ключ теперь включает форматированную дату и площадку
        unique_key = f"{event['title']}-{parsed_dt.strftime('%Y-%m-%d %H:%M')}-{event['venue_name']}"

        try:
            cursor.execute('''
                INSERT INTO events (title, description, date, ticket_link, image_url, venue_name, original_venue_id, parsed_datetime, unique_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (event['title'], event['description'], first_date_str,
                  event['ticket_link'], event['image'], event['venue_name'],
                  event['venue_id'], parsed_dt.isoformat(), unique_key))  # Сохраняем в ISO формате для сортировки
            conn.commit()
            # print(f"Событие '{event['title']}' на дату '{first_date_str}' успешно добавлено.")
        except sqlite3.IntegrityError:
            pass  # Не выводим сообщение о пропуске, если это нормально
        except IndexError:
            print(f"Событие '{event['title']}' не имеет даты. Пропускаем.")


def get_events_from_db(start_dt=None, end_dt=None):
    """
    Извлекает мероприятия из базы данных, фильтруя по диапазону дат и сортируя.
    start_dt и end_dt должны быть объектами datetime или None.
    Если start_dt и end_dt не указаны, возвращает ВСЕ мероприятия из базы.
    """
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        query = 'SELECT title, description, date, ticket_link, image_url, venue_name, parsed_datetime FROM events WHERE 1=1 '
        params = []

        # Добавляем фильтр по диапазону дат ТОЛЬКО если даты указаны
        if start_dt:
            query += 'AND parsed_datetime >= ? '
            params.append(start_dt.isoformat())

        if end_dt:
            # Для end_dt включаем все события до конца дня
            end_of_day = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            query += 'AND parsed_datetime <= ? '
            params.append(end_of_day.isoformat())

        # Всегда сортируем по дате
        query += 'ORDER BY parsed_datetime ASC'

        cursor.execute(query, params)
        db_events = cursor.fetchall()

        events_list = []
        for event_data in db_events:
            title, description, original_date_str, ticket_link, image_url, venue_name, parsed_datetime_iso = event_data

            events_list.append({
                'title': title,
                'description': description,
                'date': original_date_str,  # Сохраняем оригинальную строку для отображения
                'ticket_link': ticket_link,
                'image': image_url,
                'venue_name': venue_name
            })

        return events_list


@app.route("/")
def index():
    return render_template("index.html")


@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/history')
def event_history():
    """Отображает страницу с историей мероприятий, с фильтрацией по дате."""
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    start_dt = None
    end_dt = None

    if start_date_str:
        try:
            start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
        except ValueError:
            print(f"Некорректный формат даты начала: {start_date_str}")

    if end_date_str:
        try:
            end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
        except ValueError:
            print(f"Некорректный формат даты окончания: {end_date_str}")

    # Получаем мероприятия из базы. Если даты не указаны, получим все.
    all_db_events = get_events_from_db(start_dt=start_dt, end_dt=end_dt)

    # Группируем мероприятия по площадкам для отображения
    history_by_venue = {}
    for event in all_db_events:
        venue_name = event['venue_name']
        venue_id = slugify_filter(venue_name)
        if venue_name not in history_by_venue:
            history_by_venue[venue_name] = {'events': [], 'count': 0, 'id': venue_id}
        history_by_venue[venue_name]['events'].append(event)
        history_by_venue[venue_name]['count'] += 1

    return render_template('history.html',
                           history_by_venue=history_by_venue,
                           selected_start_date=start_date_str,  # Передаем выбранные даты для отображения в форме
                           selected_end_date=end_date_str)


@app.route('/parse', methods=['GET', 'POST'])
def parse_events():
    if request.method == 'POST':
        selected_venues = request.form.getlist('venues')
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')

        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d') if start_date_str else None
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d') if end_date_str else None

        events_by_venue = {}

        for venue in VENUES:
            if venue['id'] in selected_venues:
                events = parse_single_venue(venue['url'])

                # Добавляем название площадки и ID к каждому событию
                for event in events:
                    event['venue_name'] = venue['name']
                    event['venue_id'] = venue['id']
                    # Добавляем событие в БД, если оно еще не там (автоматически избегает дубликатов)
                    add_event_to_db(event)

                # Фильтруем события, которые будут отображены на текущей странице 'parse_events.html'
                if start_dt or end_dt:
                    events = filter_events_by_date(events, start_dt, end_dt)  # Передаем datetime объекты

                # Группируем мероприятия по названию площадки для отображения
                events_by_venue[venue['name']] = {
                    'events': events,
                    'count': len(events),
                    'id': venue['id']
                }

        return render_template('parse_events.html',
                               events_by_venue=events_by_venue,
                               selected_venues=selected_venues)

    return render_template('parse_form.html', venues=VENUES)


def parse_single_venue(url):
    """Парсит мероприятия с одной площадки"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        events = []
        for event_div in soup.find_all('div', class_='elem'):
            title_tag = event_div.find('span', class_='underline')
            title = title_tag.get_text(strip=True) if title_tag else 'Нет названия'

            description_tag = event_div.find('div', class_='d')
            description = description_tag.get_text(strip=True) if description_tag else 'Нет описания'

            dates = []
            sessions = event_div.find('div', class_='sessions')
            if sessions:
                dates = [date.get_text(strip=True) for date in sessions.find_all('span', class_='underline')]

            ticket_link = ''
            ticket_tag = event_div.find('p', class_='b')
            if ticket_tag and ticket_tag.find('a'):
                ticket_link = 'https://quicktickets.ru' + ticket_tag.find('a')['href']

            image_url = ''
            img_tag = event_div.find('img', class_='polaroid')
            if img_tag and img_tag.get('src'):
                image_url = img_tag['src']

            events.append({
                'title': title,
                'description': description,
                'dates': dates,
                'ticket_link': ticket_link,
                'image': image_url,
                'venue': url.split('/')[-1]
            })

        return events
    except Exception as e:
        print(f"Ошибка при парсинге {url}: {e}")
        return []


# Обновлена для приема datetime объектов для сравнения
def filter_events_by_date(events, start_dt=None, end_dt=None):
    """Фильтрует мероприятия по дате"""
    if not start_dt and not end_dt:
        return events

    filtered = []

    for event in events:
        for date_str in event['dates']:
            event_dt = parse_date_string_to_datetime(date_str)
            if not event_dt:
                continue  # Пропускаем события с непарсируемой датой

            # Проверяем попадает ли дата в диапазон (только дата, без времени для диапазона)
            if (not start_dt or event_dt.date() >= start_dt.date()) and \
                    (not end_dt or event_dt.date() <= end_dt.date()):
                filtered.append(event)
                break  # Если событие подходит под фильтр, нет смысла проверять другие даты для этого события
    return filtered


# Создаем фильтр slugify без использования secure_key
@app.template_filter('slugify')
def slugify_filter(text):
    """
    Конвертирует текст в slug-формат (для HTML id)
    Пример: "Театр Забайкалья" -> "teatr-zabajkalya"
    """
    text = re.sub(r'[^\w\s-]', '', text.lower())
    return re.sub(r'[-\s]+', '-', text).strip('-')


if __name__ == "__main__":
    init_db()  # Инициализируем БД при запуске приложения
    app.run(debug=True)