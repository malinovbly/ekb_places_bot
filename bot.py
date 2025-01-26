import sqlite3
import telebot
from telebot import types
from keyboa.keyboards import keyboa_maker, keyboa_combiner
from bs4 import BeautifulSoup
import requests


BOT_TOKEN = '<TOKEN>'
bot = telebot.TeleBot(BOT_TOKEN)


def add_user_to_db(user_id: int, name: str, surname: str, username: str):
    conn = sqlite3.connect('db.db')
    cur = conn.cursor()

    cur.execute(f"""
        INSERT INTO user (user_id, name, surname, username)
        SELECT ?, ?, ?, ?
        WHERE NOT EXISTS (
            SELECT 1 FROM user WHERE user_id = ?
        );
    """, (user_id, name, surname, username, user_id))
    conn.commit()


def get_ekb_attractions():
    kudago_api = 'https://kudago.com/public-api/v1.4/places'
    parameters = {
        'location': 'ekb',
        'page_size': 100,
        'categories': 'attractions'
    }
    data = requests.get(kudago_api, params=parameters)

    result = dict()
    if data.status_code == 200:
        pages_cnt = data.json()['count'] // parameters['page_size'] + 1
        for i in range(1, pages_cnt + 1):
            parameters.update({
                'page': i,
                'fields': ','.join(
                    ['id', 'title', 'address', 'images', 'description', 'site_url', 'foreign_url']
                )
            })

            page_data = requests.get(kudago_api, params=parameters)
            for place in page_data.json()['results']:
                space = place['title'].find(' ')
                if space != -1:
                    place['title'] = f"{place['title'][:space].title()}{place['title'][space:]}"
                result[place['id']] = place

    return result


def get_button_pages(buttons_per_page: int):
    if len(attractions) % buttons_per_page > 0:
        btn_pages_cnt = len(attractions) // buttons_per_page + 1
    else:
        btn_pages_cnt = len(attractions) // buttons_per_page

    btn_pages = []
    for i in range(btn_pages_cnt):
        keys = [key for key in attractions.keys()]
        page_btns = {key: attractions[key] for key in keys[i * buttons_per_page: (i + 1) * buttons_per_page]}
        titles_with_id = [(page_btns[btn_id]['title'], btn_id) for btn_id in page_btns.keys()]

        btn_page = keyboa_maker(items=titles_with_id, copy_text_to_callback=True)
        btn_pages.append(btn_page)

    return btn_pages


def make_keyboard(page: int):
    buttons = button_pages[page - 1]
    controls = [('<-', f"<- {page}"), f"стр. {page}/{len(button_pages)}", ('->', f"-> {page}")]
    kb_controls = keyboa_maker(items=controls, copy_text_to_callback=True, items_in_row=3)
    keyboard = keyboa_combiner(keyboards=(buttons, kb_controls))
    return keyboard


def send_buttons_page(call, page: int):
    keyboard = make_keyboard(page=page)
    bot.delete_message(call.message.chat.id, call.message.id)
    bot.send_message(chat_id=call.from_user.id,
                     text='Выберите интересующую вас достопримечательность',
                     reply_markup=keyboard)


def send_next_buttons_page(call):
    if int(call.data[call.data.find(' ') + 1:]) < len(button_pages):
        next_page = int(call.data[call.data.find(' ') + 1:]) + 1
        send_buttons_page(call, page=next_page)


def send_previous_buttons_page(call):
    if int(call.data[call.data.find(' ') + 1:]) > 1:
        previous_page = int(call.data[call.data.find(' ') + 1:]) - 1
        send_buttons_page(call, page=previous_page)


def send_place_info(call):
    place = attractions[int(call.data)]

    description = BeautifulSoup(place['description'], "lxml").text

    if place['foreign_url']:
        url = (f"Ссылки:\n"
               f"{place['site_url']}\n"
               f"({place['foreign_url']}, может быть устаревшей)")
    else:
        url = f"Ссылка: {place['site_url']}"

    message = (f"{place['title']}\n\n"
               f"{description}\n"
               f"Адрес: {place['address']}\n"
               f"{url}")

    if place['images'][0]['source']['name']:
        images = [types.InputMediaPhoto(image['image']) for image in attractions[int(call.data)]['images']]
        images[-1].caption = message
        bot.send_media_group(chat_id=call.from_user.id, media=images)
    else:
        bot.send_message(chat_id=call.from_user.id, text=message, disable_web_page_preview=True)


@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.from_user.id,
        text='Привет! 👋🏽\n'
             'Я помогу вам найти информацию о различных достопримечательностях Екатеринбурга\n\n'
             'Отправь команду /places'
    )
    add_user_to_db(
        message.from_user.id,
        message.from_user.first_name,
        message.from_user.last_name,
        message.from_user.username
    )


@bot.message_handler(commands=['places'])
def places(message):
    keyboard = make_keyboard(page=1)
    bot.send_message(message.from_user.id, text='Выберите интересующую вас достопримечательность', reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if '->' in call.data:
        if int(call.data[call.data.find(' ') + 1:]) < len(button_pages):
            next_page = int(call.data[call.data.find(' ') + 1:]) + 1
            keyboard = make_keyboard(page=next_page)
            bot.delete_message(call.message.chat.id, call.message.id)
            bot.send_message(chat_id=call.from_user.id,
                             text='Выберите интересующую вас достопримечательность',
                             reply_markup=keyboard)

    elif '<-' in call.data:
        if int(call.data[call.data.find(' ') + 1:]) > 1:
            previous_page = int(call.data[call.data.find(' ') + 1:]) - 1
            keyboard = make_keyboard(page=previous_page)
            bot.delete_message(call.message.chat.id, call.message.id)
            bot.send_message(chat_id=call.from_user.id,
                             text='Выберите интересующую вас достопримечательность',
                             reply_markup=keyboard)

    else:
        try:
            send_place_info(call)
        except Exception:
            pass


if __name__ == '__main__':
    attractions = get_ekb_attractions()
    button_pages = get_button_pages(buttons_per_page=8)

    bot.polling(none_stop=True, interval=0)
