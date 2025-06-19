# app.py

from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import json
import re
# import sqlite3 # УДАЛИТЬ: больше не используем sqlite3 напрямую

# Импорты для SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db_events_orm import Base, Venue, Event, \
    create_db_tables  # Импортируем наши новые модели и функцию создания таблиц

app = Flask(__name__, template_folder="startbootstrap-clean-blog-gh-pages/templates",
            static_folder="startbootstrap-clean-blog-gh-pages/static")

# Список площадок для парсинга (остается в коде для удобства инициализации)
VENUES_CONFIG = [  # Переименовал, чтобы не путать с моделью Venue
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

# --- НАСТРОЙКА SQLAlchemy ---
DATABASE_URL_EVENTS = 'sqlite:///events_orm.db'  # Та же БД, что и в db_events_orm.py
engine_events = create_engine(DATABASE_URL_EVENTS)
Session_events = sessionmaker(bind=engine_events)


# --- Инициализация БД и заполнение начальными данными (площадками) ---
def init_app_db_and_venues():
    """
    Инициализирует базу данных для приложения и заполняет таблицу venues
    данными из VENUES_CONFIG, если их там нет.
    """
    create_db_tables()  # Создаем таблицы (из db_events_orm.py)

    session = Session_events()
    try:
        for venue_data in VENUES_CONFIG:
            # Проверяем, существует ли уже площадка
            existing_venue = session.query(Venue).filter_by(original_id=venue_data['id']).first()
            if not existing_venue:
                new_venue = Venue(
                    name=venue_data['name'],
                    original_id=venue_data['id'],
                    url=venue_data['url']
                )
                session.add(new_venue)
                print(f"Добавлена площадка: {new_venue.name}")
            else:
                print(f"Площадка '{existing_venue.name}' уже существует.")
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Ошибка при инициализации площадок: {e}")
    finally:
        session.close()


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
        except ValueError:
            # Если текущий год не подходит (например, 29 февраля в невисокосном году),
            # или если дата уже прошла в этом году, но это может быть дата следующего года,
            # пробуем следующий год.
            event_dt = datetime(current_year + 1, month, day, hour, minute)

        # Корректировка года, чтобы дата была ближайшей к текущей дате
        # Если дата в будущем более чем на 6 месяцев, скорее всего, это прошлый год.
        # Это более сложно, чем просто проверка на "прошлое".
        # Лучше: если событие УЖЕ ПРОШЛО в текущем году, то это, вероятно, в следующем году
        if event_dt < datetime.now():
            # Если дата в этом году уже прошла, то, возможно, это дата следующего года
            potential_next_year_dt = event_dt.replace(year=event_dt.year + 1)
            if potential_next_year_dt >= datetime.now():  # если следующего года дата в будущем
                event_dt = potential_next_year_dt

        return event_dt
    except Exception as e:
        print(f"Не удалось распарсить дату '{date_str}': {e}")
        return None


def add_event_to_db(event_data):
    """Добавляет мероприятие в базу данных с помощью SQLAlchemy, избегая дубликатов."""
    session = Session_events()
    try:
        first_date_str = event_data['dates'][0]
        parsed_dt = parse_date_string_to_datetime(first_date_str)
        if not parsed_dt:
            print(f"Не удалось распарсить дату для события '{event_data['title']}'. Пропускаем.")
            return

        # Находим площадку по original_id (из VENUES_CONFIG)
        venue_obj = session.query(Venue).filter_by(original_id=event_data['venue_id']).first()
        if not venue_obj:
            print(
                f"Не найдена площадка с original_id '{event_data['venue_id']}'. Пропускаем событие '{event_data['title']}'.")
            return

        # Проверяем на дубликаты используя уникальный ключ/уникальный constrain
        # UniqueConstraint в модели Event уже покроет это, но можем явно проверить, если хотим
        # более гранулярный контроль или логирование.
        # Создадим уникальный ключ для проверки (хотя constrain в БД это сделает)
        # UniqueConstraint: ('title', 'parsed_datetime', 'venue_id')
        existing_event = session.query(Event).filter(
            Event.title == event_data['title'],
            Event.parsed_datetime == parsed_dt,
            Event.venue_id == venue_obj.id
        ).first()

        if existing_event:
            # print(f"Событие '{event_data['title']}' на '{first_date_str}' ({event_data['venue_name']}) уже существует. Пропускаем.")
            return

        new_event = Event(
            title=event_data['title'],
            description=event_data['description'],
            original_date_str=first_date_str,
            parsed_datetime=parsed_dt,
            ticket_link=event_data['ticket_link'],
            image_url=event_data['image'],
            venue_id=venue_obj.id,  # Используем ID объекта Venue
            # Создаем уникальный ключ для отладки, но основной уникальности добьемся через UniqueConstraint
            unique_key=f"{event_data['title']}-{parsed_dt.strftime('%Y-%m-%d %H:%M')}-{venue_obj.original_id}"
        )
        session.add(new_event)
        session.commit()
        # print(f"Событие '{event_data['title']}' на дату '{first_date_str}' успешно добавлено.")
    except Exception as e:
        session.rollback()
        print(f"Ошибка при добавлении события '{event_data['title']}' в БД: {e}")
    finally:
        session.close()


def get_events_from_db(start_dt=None, end_dt=None):
    """
    Извлекает мероприятия из базы данных, фильтруя по диапазону дат и сортируя.
    start_dt и end_dt должны быть объектами datetime или None.
    """
    session = Session_events()
    try:
        query = session.query(Event).join(Venue)  # Делаем JOIN с Venue для получения имени площадки

        if start_dt:
            query = query.filter(Event.parsed_datetime >= start_dt)

        if end_dt:
            # Для end_dt включаем все события до конца дня
            end_of_day = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            query = query.filter(Event.parsed_datetime <= end_of_day)

        query = query.order_by(Event.parsed_datetime.asc())

        db_events = query.all()

        events_list = []
        for event_obj in db_events:
            events_list.append({
                'title': event_obj.title,
                'description': event_obj.description,
                'date': event_obj.original_date_str,
                'ticket_link': event_obj.ticket_link,
                'image': event_obj.image_url,
                'venue_name': event_obj.venue.name,  # Доступ к имени площадки через связь
                'venue_id': event_obj.venue.original_id  # ID площадки из VENUES_CONFIG
            })
        return events_list
    except Exception as e:
        print(f"Ошибка при извлечении событий из БД: {e}")
        return []
    finally:
        session.close()


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
        venue_id = event['venue_id']  # Используем уже полученный venue_id из БД
        if venue_name not in history_by_venue:
            history_by_venue[venue_name] = {'events': [], 'count': 0, 'id': venue_id}
        history_by_venue[venue_name]['events'].append(event)
        history_by_venue[venue_name]['count'] += 1

    return render_template('history.html',
                           history_by_venue=history_by_venue,
                           selected_start_date=start_date_str,
                           selected_end_date=end_date_str)


@app.route('/parse', methods=['GET', 'POST'])
def parse_events():
    if request.method == 'POST':
        selected_venues_ids = request.form.getlist('venues')  # Получаем original_id
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')

        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d') if start_date_str else None
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d') if end_date_str else None

        events_by_venue_display = {}  # Для отображения на parse_events.html

        for venue_config in VENUES_CONFIG:
            if venue_config['id'] in selected_venues_ids:
                parsed_events_raw = parse_single_venue(venue_config['url'])

                current_venue_events_for_display = []

                for event_raw in parsed_events_raw:
                    # Добавляем название площадки и ID к каждому событию для удобства
                    # и для передачи в add_event_to_db
                    event_raw['venue_name'] = venue_config['name']
                    event_raw['venue_id'] = venue_config['id']  # Используем original_id

                    # Добавляем событие в БД (ORM-версия)
                    add_event_to_db(event_raw)

                    # Фильтруем события для отображения на текущей странице 'parse_events.html'
                    # Если даты не заданы, все парсенные события пойдут в отображение
                    # Иначе, только те, что в диапазоне
                    if not start_dt and not end_dt:
                        current_venue_events_for_display.append(event_raw)
                    else:
                        # Проверяем каждую дату события, так как у события может быть несколько дат
                        for date_str in event_raw['dates']:
                            event_dt = parse_date_string_to_datetime(date_str)
                            if event_dt and \
                                    (not start_dt or event_dt.date() >= start_dt.date()) and \
                                    (not end_dt or event_dt.date() <= end_dt.date()):
                                current_venue_events_for_display.append(event_raw)
                                break  # Добавляем событие один раз, если хоть одна дата подходит

                # Группируем мероприятия по названию площадки для отображения
                events_by_venue_display[venue_config['name']] = {
                    'events': current_venue_events_for_display,
                    'count': len(current_venue_events_for_display),
                    'id': venue_config['id']
                }

        return render_template('parse_events.html',
                               events_by_venue=events_by_venue_display,
                               selected_venues=selected_venues_ids)

    return render_template('parse_form.html', venues=VENUES_CONFIG)  # Передаем VENUES_CONFIG


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
            if not dates:  # Если дат нет, берем из основного блока
                date_tag = event_div.find('p', class_='a')
                if date_tag:
                    dates.append(date_tag.get_text(strip=True))

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
                'dates': dates,  # Список дат
                'ticket_link': ticket_link,
                'image': image_url,
                # 'venue': url.split('/')[-1] # Это больше не нужно, venue_id будет добавляться позже
            })

        return events
    except Exception as e:
        print(f"Ошибка при парсинге {url}: {e}")
        return []


# Удаляем filter_events_by_date, так как фильтрация теперь происходит на уровне БД в get_events_from_db
# И в parse_events при отображении.

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
    init_app_db_and_venues()  # Инициализируем БД и площадки при запуске приложения
    app.run(debug=True)