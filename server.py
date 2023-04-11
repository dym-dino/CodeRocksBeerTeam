# -*- coding: utf-8 -*-
# Main script
# Written by Dinosaur
#                __
#               / _)
#      _.----._/ /
#     /         /
#  __/ (  | (  |
# /__.-'|_|--|_|
# ---------------------------------------------------------------------------------------------------------------------
# import libraries
import datetime
import io
import json
import os
from functools import wraps

import fleep
from flask import Flask, render_template, send_from_directory, Response, request, redirect, send_file, flash
from flask_wtf import FlaskForm
from telebot import TeleBot
from wtforms import StringField, TextAreaField, SubmitField, SelectMultipleField, widgets
from wtforms.validators import DataRequired

import config
from config import path
from database import Database
from funcitons import print_error, create_password, get_username
from mailing import Mailing

# ---------------------------------------------------------------------------------------------------------------------
# CONFIG

# connect to database
db = Database()

# flask app
app = Flask(__name__, static_folder=os.path.join(path, 'static'), template_folder=os.path.join(path, 'templates'))
app.config['SECRET_KEY'] = config.FLASK_SECRET_KEY

# telegram bot
bot = TeleBot(config.BOT_TOKEN)

# for mailings
mailings = {}


# --------------------------------------------------------------------------------------------------------------------
# CHECK AUTH

# check auth function
def check_auth(username, password):
    if username == config.ADMIN_LOGIN and password == config.ADMIN_PASSWORD:
        return True
    else:
        return False


# login page
def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})


# authenticate decorator
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if auth is None:
            return authenticate()

        if not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------------------------------------------------
# ROUTES

# favicon
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico',
                               mimetype='image/vnd.microsoft.icon')


# error page
@app.errorhandler(Exception)
def all_exception_handler(err):
    print_error(err)
    return render_template('error.html')


# main page
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


# production info
@app.route('/production', methods=['GET'])
def production():
    images = [i for i in os.listdir(os.path.join(path, 'static')) if 'production' in i]
    return render_template('production.html', images=images, images_i=[i for i in range(1, len(images))])


# products info
@app.route('/products', methods=['GET'])
def products():
    images = [i for i in os.listdir(os.path.join(path, 'static')) if 'product' in i and 'production' not in i]
    return render_template('products.html', images=images, images_i=[i for i in range(1, len(images))])


# --------------------------------------------------------------------------------------------------------------------
# ADMIN PANEL


# main admin panel page
@app.route('/admin', methods=['GET'])
@requires_auth
def admin():
    unread = db.unread_messages()
    return render_template('admin.html', unread=len(unread))


# mailing statuses
@app.route('/mailing_status', methods=['GET'])
@requires_auth
def mailing_status():
    try:
        mails = [[i, mailings[i].time, len(mailings[i].send), len(mailings[i].problem_chats),
                  mailings[i].work, len(mailings[i].users)] for i in mailings]
        return render_template('mailing_status.html', mails=mails)

    except Exception as e:
        print_error(e)
        return render_template('error.html')


# start mailing
@app.route('/mailing', methods=['GET', 'POST'])
@requires_auth
def mailing():
    try:
        if request.method == 'POST':
            form = request.form
            form = dict(form)
            mime = None
            filename = None
            text = form['text'] if 'text' in form else None
            if 'file' in request.files:
                files = request.files['file']
                files = files.read()
                if len(files) < 5:
                    files = None
                else:
                    mime = None
                    try:
                        mime = request.files['file'].mimetype
                    except Exception:
                        pass

                    if mime is None:
                        mime = fleep.get(files).mime[0]
                    filename = request.files['file'].filename

            else:
                files = None

            if text is None and files is None:
                return render_template('error.html')

            else:
                keyboard = None
                all_users = db.users_get_all()
                new_mailing = Mailing(bot=bot, mail_users=all_users, text=text, files=files,
                                      mime=mime, filename=filename, keyboard=keyboard)
                new_mail_id = create_password()
                mailings[new_mail_id] = new_mailing
                new_mailing.start()

                return redirect('/mailing_status')

        else:
            return render_template('mailing.html')

    except Exception as e:
        print_error(e)
        return render_template('error.html')


# get users base
@app.route('/users_base/', methods=['GET'])
@requires_auth
def users_base():
    try:
        file = db.users_statistic()
        return send_file(file, as_attachment=True, download_name='База пользователей.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        print_error(e)
        return render_template('error.html')


# dialog attachment
@app.route('/dialog_message_photo/<int:message_id>', methods=['GET'])
@requires_auth
def dialog_message_photo(message_id):
    try:
        file = db.messages_get_one(message_id)[6]
        f = io.BytesIO()
        f.write(file)
        f.seek(0)
        mime = fleep.get(file.tobytes()).mime[0]
        return send_file(f, mimetype=mime, as_attachment=True,
                         download_name=f'file.{fleep.get(file.tobytes()).extension[0]}')

    except Exception as e:
        print_error(e)
        return render_template('error.html')


# dialogs list page
@app.route('/dialogs/', methods=['GET'])
@requires_auth
def dialogs():
    try:
        users_with_dialogs = db.users_get_with_dialogs()
        unread = db.unread_messages()
        return render_template('dialogs.html', users=users_with_dialogs, lu=len(users_with_dialogs), unread=len(unread))

    except Exception as e:
        print_error(e)
        return render_template('error.html')


# dialog page
@app.route('/dialog/<int:user_id>', methods=['GET'])
@requires_auth
def dialog(user_id):
    try:
        user = db.users_get_one(user_id)

        user_info = user[-1]
        user_info['unread'] = 'False'
        db.users_update_info(user_id, 'info', json.dumps(user_info))

        user = [user_id, get_username(user[-1])]
        users_message = db.messages_get_all_by_user(user_id)

        return render_template('dialog.html', user=user, messages=users_message)

    except Exception as e:
        print_error(e)
        return render_template('error.html')


# answer in dialog
@app.route('/dialog_answer/<int:user_id>/', methods=['GET', 'POST'])
@requires_auth
def dialog_answer(user_id):
    try:
        if request.method == 'POST':
            form = request.form
            form = dict(form)
            text = form['text'] if 'text' in form else None
            if 'file' in request.files:
                files = dict(request.files)
                files = files['file']
                files = files.read()
                if len(files) < 5:
                    files = None

            else:
                files = None

            if text is None and files is None:
                return render_template('error.html')

            else:
                new_message = (user_id, 'ответ', datetime.datetime.now(), True, text, files)
                db.messages_add(new_message)

                if files is not None:
                    mime = fleep.get(files).mime[0]
                    try:
                        if 'image' in mime:
                            bot.send_photo(user_id, photo=files, caption=text)

                        elif 'video' in mime:
                            bot.send_video(user_id, video=files, caption=text)

                        else:
                            file = io.BytesIO(files)
                            file.name = request.files['file'].filename
                            bot.send_document(user_id, document=file, caption=text)
                    except Exception as e:
                        print_error(e)

                else:
                    try:
                        bot.send_message(user_id, text)
                    except Exception as e:
                        print_error(e)

                return redirect(f'/dialog/{user_id}')
        else:
            return redirect(f'/dialog/{user_id}')

    except Exception as e:
        print_error(e)
        return render_template('error.html')


# setup roles
@app.route('/roles_setup', methods=['GET'])
@requires_auth
def roles_setup():
    return render_template('roles_setup.html', roles=db.roles_get_all())


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class RoleForm(FlaskForm):
    name = StringField("Название", validators=[DataRequired()])
    duties = MultiCheckboxField("Должности", choices=[(i[0], i[1]) for i in db.duties_get_all()], coerce=int)
    submit = SubmitField("Добавить")


# add role
@app.route('/add_role', methods=['GET', 'POST'])
@requires_auth
def add_role():
    form = RoleForm()
    if request.method == 'POST':
        try:
            name = form.name.data
            duties = [int(i) for i in form.duties.data]
            role = db.roles_get_by_name(name)
            if role is not None:
                flash('Должность с таким именем уже существует', 'add_role')
                return render_template('add_role.html', form=form)

            else:
                new_role = (name, duties)
                db.roles_add(new_role)
            return redirect('/roles_setup')
        except Exception as e:
            print_error(e)
            return render_template('add_role.html', form=form)

    else:
        return render_template('add_role.html', form=form)


# edit role
@app.route('/edit_role/<int:role_id>', methods=['GET', 'POST'])
@requires_auth
def edit_role(role_id):
    role = db.roles_get_one(role_id)
    if request.method == 'POST':
        form = RoleForm()
        try:
            name = form.name.data
            duties = [int(i) for i in form.duties.data]

            if name != role[1]:
                new_duty = db.roles_get_by_name(name)
                if new_duty is not None:
                    flash('Должность с таким именем уже существует', 'add_role')
                    return render_template('edit_role.html', form=form, role=role)
                else:
                    db.roles_update_info(role_id, 'name', name)

            if duties != role[2]:
                db.roles_update_info(role_id, 'duties', duties)

            flash('Должность изменена', 'edit_role_success')

            return render_template('edit_role.html', form=form, role=role)
        except Exception as e:
            print_error(e)

        return render_template('edit_role.html', form=form, role=role)
    else:
        form = RoleForm()
        form.name.data = role[1]
        form.duties.data = role[2]

        return render_template('edit_role.html', form=form, role=role)


@app.route('/delete_role/<int:role_id>', methods=['GET'])
@requires_auth
def delete_role(role_id):
    db.roles_delete(role_id)
    access_codes = db.access_codes_get_by_role(role_id)
    for code in access_codes:
        db.access_codes_delete(code[0])
    return redirect('/roles_setup')


# setup duties
@app.route('/duties_setup', methods=['GET'])
@requires_auth
def duties_setup():
    return render_template('duties_setup.html', duties=db.duties_get_all())


class DutyForm(FlaskForm):
    name = StringField("Название", validators=[DataRequired()])
    about = TextAreaField("Описание", validators=[DataRequired()])
    question = StringField("Вопрос", validators=[DataRequired()])
    correct_answer = StringField("Правильный ответ", validators=[DataRequired()])
    incorrect_answer_1 = StringField("Неправильный ответ №1", validators=[DataRequired()])
    incorrect_answer_2 = StringField("Неправильный ответ №2", validators=[DataRequired()])
    incorrect_answer_3 = StringField("Неправильный ответ №3", validators=[DataRequired()])
    submit = SubmitField("Добавить")


# add duty
@app.route('/add_duty', methods=['GET', 'POST'])
@requires_auth
def add_duty():
    form = DutyForm()
    if form.validate_on_submit():
        try:
            name = form.name.data
            about = form.about.data
            question = form.question.data
            answers = {'correct': form.correct_answer.data,
                       'incorrect': [i.data for i in [form.incorrect_answer_1, form.incorrect_answer_2,
                                                      form.incorrect_answer_3]]}
            duty = db.duties_get_by_name(name)
            if duty is not None:
                flash('Обязанность с таким именем уже существует', 'add_duty')
                return render_template('add_duty.html', form=form)

            else:
                new_duty = (name, about, question, json.dumps(answers))
                db.duties_add(new_duty)
            return redirect('/duties_setup')
        except Exception as e:
            print_error(e)
            return render_template('add_duty.html', form=form)

    else:
        return render_template('add_duty.html', form=form)


# edit duty
@app.route('/edit_duty/<int:duty_id>', methods=['GET', 'POST'])
@requires_auth
def edit_duty(duty_id):
    duty = db.duties_get_one(duty_id)
    form = DutyForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                name = form.name.data
                about = form.about.data
                question = form.question.data
                answers = {'correct': form.correct_answer.data,
                           'incorrect': [i.data for i in [form.incorrect_answer_1, form.incorrect_answer_2,
                                                          form.incorrect_answer_3]]}

                if name != duty[1]:
                    new_duty = db.duties_get_by_name(name)
                    if new_duty is not None:
                        flash('Обязанность с таким именем уже существует', 'add_duty')
                        return render_template('edit_duty.html', form=form, duty=duty)
                    else:
                        db.duties_update_info(duty_id, 'name', name)

                if about != duty[2]:
                    db.duties_update_info(duty_id, 'about', about)

                if question != duty[3]:
                    db.duties_update_info(duty_id, 'question', question)

                if answers != duty[4]:
                    db.duties_update_info(duty_id, 'answers', json.dumps(answers))

                flash('Обязанность изменена', 'edit_duty_success')

                return render_template('edit_duty.html', form=form, duty=duty)
            except Exception as e:
                print_error(e)

            return render_template('edit_duty.html', form=form, duty=duty)
    else:
        form.name.data = duty[1]
        form.about.data = duty[2]
        form.question.data = duty[3]
        form.correct_answer.data = duty[4]['correct']
        form.incorrect_answer_1.data = duty[4]['incorrect'][0]
        form.incorrect_answer_3.data = duty[4]['incorrect'][1]
        form.incorrect_answer_2.data = duty[4]['incorrect'][2]

        return render_template('edit_duty.html', form=form, duty=duty)


# delete duty
@app.route('/delete_duty/<int:duty_id>', methods=['GET'])
@requires_auth
def delete_duty(duty_id):
    db.duties_delete(duty_id)
    roles = db.roles_get_by_duty(duty_id)
    for role in roles:
        duties = roles[2]
        if duty_id in duties:
            duties.remove(duty_id)
            db.roles_update_info(role[0], 'duties', duties)
    return redirect('/duties_setup')


@app.route('/access_codes', methods=['GET', 'POST'])
@requires_auth
def access_codes():
    return render_template('access_codes.html', codes=db.access_codes_get_all())


# ---------------------------------------------------------------------------------------------------------------------
# starting the web server
if __name__ == '__main__':
    while True:
        try:
            app.run(host='0.0.0.0', threaded=True, debug=True)
        except Exception as error:
            print_error(error)
