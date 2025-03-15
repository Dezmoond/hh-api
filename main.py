import requests
import json
from collections import Counter #подсчета частоты слов
import re

# Функция для получения данных о вакансиях
def get_vacancies(job_title, area='1', per_page=100):
    url = 'https://api.hh.ru/vacancies'
    params = {
        'text': job_title,
        'area': 1,  # Москва - 1, можно указать другой регион
        'per_page': per_page
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    print(response)
    return response.json()['items']

# Функция для фильтрации ключевых навыков
def extract_skills(description):
    # Список релевантных навыков
    relevant_skills = ["python", "django", "flask", "sqlalchemy"]
    found_skills = []

    # Удаление HTML-тегов и приведение текста к нижнему регистру
    cleaned_text = re.sub(r'<.*?>', '', description.lower())

    # Поиск навыков по релевантному списку
    for skill in relevant_skills:
        if skill in cleaned_text:
            found_skills.append(skill)

    return found_skills

# Функция для анализа требований и зарплат
def analyze_vacancies(vacancies):
    skills_counter = Counter()
    total_salary = 0
    count_salary = 0

    for vacancy in vacancies:
        description = vacancy['snippet']['requirement'] or ''
        skills = extract_skills(description)
        skills_counter.update(skills)

        salary = vacancy.get('salary')
        if salary and salary.get('from'):
            total_salary += salary['from']
            count_salary += 1

    total_vacancies = len(vacancies)
    avg_salary = total_salary / count_salary if count_salary else 0

    skills_stats = {skill: {
        "count": count,
        "percentage": round(count / total_vacancies * 100, 1)
    } for skill, count in skills_counter.most_common()}

    return {
        "total_vacancies": total_vacancies,
        "average_salary": avg_salary,
        "skills": skills_stats
    }

# Сохранение данных в JSON-файл
def save_to_json(data, filename='vacancies_analysis.json'):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    job_title = "Python developer"
    vacancies = get_vacancies(job_title)
    analysis_result = analyze_vacancies(vacancies)
    save_to_json(analysis_result)
    print(f"Результат сохранен в файл: vacancies_analysis.json")