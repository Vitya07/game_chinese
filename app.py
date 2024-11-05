from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask import jsonify
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(150), nullable=False)
    documents = db.relationship('Document', backref='owner', lazy=True)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    characters = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Внешний ключ

    correct_characters = db.Column(db.Text, default='')  # Хранит правильные иероглифы
    incorrect_characters = db.Column(db.Text, default='')  # Хранит неправильные иероглифы

    def add_correct_character(self, character):
        # Add to correct_characters if not already there
        if character not in self.correct_characters.split():
            if self.correct_characters:
                self.correct_characters += f' {character}'
            else:
                self.correct_characters = character

        # Add to main characters field if not already there
        if character not in self.characters.split():
            self.characters += f' {character}'
        
        db.session.commit()

    def add_incorrect_character(self, character):
        # Add to incorrect_characters if not already there
        if character not in self.incorrect_characters.split():
            if self.incorrect_characters:
                self.incorrect_characters += f' {character}'
            else:
                self.incorrect_characters = character

        # Add to main characters field if not already there
        if character not in self.characters.split():
            self.characters += f' {character}'
        
        db.session.commit()


with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
        flash('Неверное имя пользователя или пароль', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    documents = Document.query.filter_by(user_id=current_user.id).all()
    return render_template('index.html', documents=documents)

@app.route('/create_document', methods=['GET', 'POST'])
def create_document():
    if request.method == 'POST':
        name = request.form['name']
        characters = request.form['characters']
        
        # Создаем новый экземпляр документа
        new_document = Document(name=name, characters=characters, user_id=current_user.id)

        # Добавляем документ в сессию и коммитим
        db.session.add(new_document)
        db.session.commit()

        flash('Документ успешно создан!', 'success')
        return redirect(url_for('index'))  # Перенаправление на главную страницу или страницу документов

    return render_template('create_document.html')


@app.route('/edit_document/<int:doc_id>', methods=['GET', 'POST'])
@login_required
def edit_document(doc_id):
    document = Document.query.get_or_404(doc_id)
    if request.method == 'POST':
        document.name = request.form['name']
        document.characters = request.form['characters']
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('edit_document.html', document=document)

@app.route('/delete_document/<int:doc_id>')
@login_required
def delete_document(doc_id):
    document = Document.query.get_or_404(doc_id)
    db.session.delete(document)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/play/<int:doc_id>', methods=['GET', 'POST'])
def play(doc_id):
    document = Document.query.get(doc_id)
    characters = document.characters.split()  # Разделяем иероглифы

    mode = request.args.get('mode', 'order')  # Получаем режим из URL-параметра, по умолчанию - 'order'

    # Если режим "random" и порядок символов не сохранен в сессии, перемешиваем
    if mode == 'random':
        if 'character_order' not in session:
            random.shuffle(characters)  # Перемешиваем символы один раз
            session['character_order'] = characters  # Сохраняем перемешанные символы в сессии
            session['character_index'] = 0  # Начинаем с первого символа

    # Получаем текущий порядок символов из сессии
    character_order = session.get('character_order', characters)  # Используем сохраненный порядок или оригинальный
    character_index = session.get('character_index', 0)  # Индекс текущего символа

    # Обрабатываем POST-запрос (игрок делает выбор)
    if request.method == 'POST':
        choice = request.form.get('choice')

        # Добавляем выбранный символ в правильные или неправильные ответы
        if choice == 'correct':
            document.add_correct_character(character_order[character_index])
        else:
            document.add_incorrect_character(character_order[character_index])

        character_index += 1  # Переходим к следующему символу
        session['character_index'] = character_index  # Сохраняем новый индекс в сессии
        db.session.commit()

        # Если дошли до конца списка символов, переходим на страницу результатов
        if character_index >= len(character_order):
            session.pop('character_order', None)  # Очищаем порядок символов из сессии
            session.pop('character_index', None)  # Очищаем индекс из сессии
            return redirect(url_for('results', doc_id=doc_id))

        return render_template('game.html', document=document, character=character_order[character_index], character_index=character_index)

    # Сбрасываем перед началом игры
    document.correct_characters = ""
    document.incorrect_characters = ""
    db.session.commit()

    # Если игра начинается, нужно перемешать символы
    if mode == 'random':
        random.shuffle(characters)  # Перемешиваем символы
        session['character_order'] = characters  # Сохраняем перемешанные символы в сессии
        session['character_index'] = 0  # Начинаем с первого символа

    # Отображаем первый символ
    character_order = session.get('character_order', characters)  # Получаем порядок символов
    return render_template('game.html', document=document, character=character_order[0], character_index=0)

    # Сбрасываем перед началом игры
    document.correct_characters = ""
    document.incorrect_characters = ""
    db.session.commit()

    # Отображаем первый символ
    return render_template('game.html', document=document, character=character_order[character_index], character_index=character_index)

@app.route('/results/<int:doc_id>')
def results(doc_id):
    document = Document.query.get(doc_id)
    correct_words = document.correct_characters.strip().split()
    incorrect_words = document.incorrect_characters.strip().split()

    return render_template('results.html', document=document, correct_words=correct_words, incorrect_words=incorrect_words)


@app.route('/delete_selected_words', methods=['POST'])
@login_required
def delete_selected_words():
    data = request.json
    words = data['words']
    doc_id = data['doc_id']
    
    document = Document.query.get_or_404(doc_id)

    for item in words:
        word = item['word']
        character_type = item['type']
        
        if character_type == 'correct':
            correct_chars = document.correct_characters.split()
            if word in correct_chars:
                correct_chars.remove(word)
            document.correct_characters = ' '.join(correct_chars)

            # Удаляем иероглиф из основного текста
            characters = document.characters.split()
            if word in characters:
                characters.remove(word)
            document.characters = ' '.join(characters)

        elif character_type == 'incorrect':
            incorrect_chars = document.incorrect_characters.split()
            if word in incorrect_chars:
                incorrect_chars.remove(word)
            document.incorrect_characters = ' '.join(incorrect_chars)

            # Удаляем иероглиф из основного текста
            characters = document.characters.split()
            if word in characters:
                characters.remove(word)
            document.characters = ' '.join(characters)

    db.session.commit()
    return jsonify({"success": True})

@app.route('/edit_selected_words', methods=['POST'])
@login_required
def edit_selected_words():
    data = request.json
    words = data.get('words', [])
    doc_id = data.get('doc_id')

    # Получаем документ по id
    document = Document.query.get_or_404(doc_id)

    try:
        for word_data in words:
            original_word = word_data['originalWord']
            new_word = word_data['newWord']
            word_type = word_data['type']

            if word_type == 'correct':
                # Обновляем корректные иероглифы
                correct_chars = document.correct_characters.split()
                correct_chars = [new_word if word == original_word else word for word in correct_chars]
                document.correct_characters = ' '.join(correct_chars)

            elif word_type == 'incorrect':
                # Обновляем некорректные иероглифы
                incorrect_chars = document.incorrect_characters.split()
                incorrect_chars = [new_word if word == original_word else word for word in incorrect_chars]
                document.incorrect_characters = ' '.join(incorrect_chars)

            # Обновляем также основной текст, если слово там присутствует
            characters = document.characters.split()
            characters = [new_word if word == original_word else word for word in characters]
            document.characters = ' '.join(characters)

        # Сохраняем изменения в базе данных
        db.session.commit()
        return jsonify(success=True)
    
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

@app.route('/add_character', methods=['POST'])
@login_required
def add_character():
    data = request.json
    character = data.get('character')
    character_type = data.get('type')
    doc_id = data.get('doc_id')

    # Retrieve the document by ID
    document = Document.query.get_or_404(doc_id)

    try:
        # Add the character based on the specified type
        if character_type == 'correct':
            document.add_correct_character(character)
        elif character_type == 'incorrect':
            document.add_incorrect_character(character)
        elif character_type == 'both':
            document.add_correct_character(character)
            document.add_incorrect_character(character)
        
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500



