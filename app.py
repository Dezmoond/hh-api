from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import json

import re

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
@app.route("/")
def index():
    return render_template("index.html")


@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/parse', methods=['GET', 'POST'])
def parse_events():
    if request.method == 'POST':
        selected_venues = request.form.getlist('venues')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        # Словарь для группировки мероприятий по площадкам
        events_by_venue = {}

        for venue in VENUES:
            if venue['id'] in selected_venues:
                events = parse_single_venue(venue['url'])

                if start_date or end_date:
                    events = filter_events_by_date(events, start_date, end_date)

                # Группируем мероприятия по названию площадки
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
        for event in soup.find_all('div', class_='elem'):
            title = event.find('span', class_='underline').get_text(strip=True) if event.find('span',
                                                                                              class_='underline') else 'Нет названия'
            description = event.find('div', class_='d').get_text(strip=True) if event.find('div',
                                                                                           class_='d') else 'Нет описания'

            dates = []
            sessions = event.find('div', class_='sessions')
            if sessions:
                dates = [date.get_text(strip=True) for date in sessions.find_all('span', class_='underline')]

            ticket_link = ''
            ticket_tag = event.find('p', class_='b')
            if ticket_tag and ticket_tag.find('a'):
                ticket_link = 'https://quicktickets.ru' + ticket_tag.find('a')['href']

            image_url = ''
            img_tag = event.find('img', class_='polaroid')
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


def filter_events_by_date(events, start_date=None, end_date=None):
    """Фильтрует мероприятия по дате"""
    if not start_date and not end_date:
        return events

    filtered = []
    start_dt = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
    end_dt = datetime.strptime(end_date, '%Y-%m-%d') if end_date else None

    for event in events:
        for date_str in event['dates']:
            try:
                # Парсим дату из строки (пример: "15 мая 19:00")
                day, month_name, time = date_str.split()
                month = RU_MONTHS[month_name.lower()]
                hour, minute = map(int, time.split(':'))
                year = datetime.now().year
                event_dt = datetime(year, month, int(day), hour, minute)

                # Проверяем попадает ли дата в диапазон
                if (not start_dt or event_dt >= start_dt) and \
                        (not end_dt or event_dt <= end_dt):
                    filtered.append(event)
                    break
            except:
                continue

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
    app.run(debug=True)