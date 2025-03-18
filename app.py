from flask import Flask, render_template, request, jsonify
from main import get_vacancies, analyze_vacancies, save_to_json  # Импортируем функции
import json
import os

app = Flask(__name__, template_folder="startbootstrap-clean-blog-gh-pages/templates", static_folder="startbootstrap-clean-blog-gh-pages/static")
analysis_data = {}
@app.route("/")
def index():
    return render_template("index.html")

@app.route('/contact')
def contact():
    return render_template('contact.html')  # Рендерим страницу contact.html

# Страница с анализом вакансий
@app.route('/post', methods=['GET', 'POST'])
def post():
    if request.method == 'POST':
        # Получаем значение job_title из формы
        job_title = request.form.get('job_title')
        vacancies = get_vacancies(job_title)  # Получаем вакансии с введенным job_title
        analysis_result = analyze_vacancies(vacancies)  # Анализируем вакансии
        save_to_json(analysis_result)  # Сохраняем результат в JSON
        global analysis_data
        analysis_data = analysis_result  # Сохраняем результат в глобальную переменную
        return render_template('post.html', analysis_result=analysis_result)

    return render_template('post.html')

# Обработка запроса на анализ вакансий через POST
@app.route('/analyze', methods=['POST'])
def analyze():
    # Получаем данные, переданные с фронтенда
    data = request.get_json()
    job_title = data.get('job_title')

    if job_title:
        # Получаем вакансии с введенным job_title
        vacancies = get_vacancies(job_title)
        # Анализируем вакансии
        analysis_result = analyze_vacancies(vacancies)
        # Сохраняем результат в глобальную переменную
        global analysis_data
        analysis_data = analysis_result
        # Сохраняем результат в JSON
        save_to_json(analysis_result)

        return jsonify({'message': 'Анализ завершен!'})
    else:
        return jsonify({'error': 'Не указан job_title'}), 400

# Маршрут для загрузки результатов анализа
@app.route('/results', methods=['GET'])
def results():
    return jsonify(analysis_data)  # Возвращаем результаты анализа в формате JSON
if __name__ == "__main__":
    app.run(debug=True)
