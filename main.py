import datetime
import random
from datetime import timezone
from fuzzywuzzy import fuzz

import telegram.ext
import logging
import sqlite3
import json

from telegram import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, \
    ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, Filters, MessageHandler, ConversationHandler
class Player(object):
    def __init__(self, id):
        self.id = id

class GamePlayer:
    def __init__(self, ply):
        self.ply = ply
        self.ingame = True
        self.dead = False
        self.admin = False
    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True)

class Game(object):
    def __init__(self, id):
        self.id = id
        self.players = []
        self.maps = {}
    def try_join(self, pll):
        gp = GamePlayer(pll)
        if len(self.players) == 0:
            gp.admin = True
        pll.game = self.id
        self.players.append(gp)
        db_savegame(self)
        db_saveplayer(pll)
    def get_gp(self, pll):
        for xx in self.players:
            if xx.ply.id == pll.id:
                return xx
    def pl_quit(self):
        pass


def get_anketa(user):
    result = ""
    result += user.name + ", "
    result += "мне " + str(user.age) + ", "
    result += "отряд " + str(user.otryad) + "."
    #result += "живу в " + str(user.room) + " комнате."
    result += " О себе: " + user.interests
    return result
def build_menu(buttons, n_cols,
               header_buttons=None,
               footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, [header_buttons])
    if footer_buttons:
        menu.append([footer_buttons])
    return menu

def tg_ontext(update, context):
    user = db_getplayer(update.message.from_user.id)
    if user == None:
        start(update, context)
        return

    shouldSave = True
    text = update.message.text
    print(user.username + " -> " + text)
    if user.state == 0:
        response = "Отлично! Вот правила игры!"
        user.state = 1
        user.name = update.message.text
        reply_keyboard = [['Я согласен']]
        reply_markup = ReplyKeyboardMarkup(
             reply_keyboard, one_time_keyboard=True,resize_keyboard=True
        )
        context.bot.send_message(chat_id=update.effective_chat.id, text=response, reply_markup=reply_markup)
        db_saveplayer(user)
        return NAME
    elif user.state == 1:
        if update.message.text != "Я согласен":
            response = "Ты должен согласиться с правилами"
            reply_keyboard = [['Я согласен']]
            reply_markup = ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, resize_keyboard=True
            )
            context.bot.send_message(chat_id=update.effective_chat.id, text=response, reply_markup=reply_markup)
            return NAME

        user.state = 2
        on_rules_accepted(update, context)
        db_saveplayer(user)
        return NAME
    elif user.state == 2:
        if update.message.text == "Создать игру":
            user.state = 4
            response = "Ваша игра была создана: Ее ID: "
            game = db_creategame(user)
            game.try_join(user)
            response += str(game.id)
            response += ". Отправьте ее другим чтобы присоединиться"

        elif update.message.text == "Присоединиться к игре":
            user.state = 3
            response = "Введите ваш код приглашения:"

        else:
            on_rules_accepted(update, context)
            return NAME
    elif user.state == 3:
        if not update.message.text.isdigit():
            context.bot.send_message(chat_id=update.effective_chat.id, text="Неверный ввод ID")
            user.state = 1
            db_saveplayer(user)
            on_rules_accepted(update, context)
            return DEFAULT
        it = db_getgame(int(update.message.text))
        if it == None or it.id == 0:
            context.bot.send_message(chat_id=update.effective_chat.id, text="Такой игры не существует")
            user.state = 1
            db_saveplayer(user)
            on_rules_accepted(update, context)
            return DEFAULT
        it.try_join(user)
        db_savegame(it)
        user.state = 4
        db_saveplayer(user)
        context.bot.send_message(chat_id=update.effective_chat.id, text="Вы в игре :)")
    elif user.state == 4:
        gm = db_getgame(user.game)
        game_player = gm.get_gp(user)
        context.bot.send_message(chat_id=update.effective_chat.id, text="Вы в игре " + json.dumps(game_player, default=vars))


        pass


    if user.state < 7 and 'response' in locals() and len(response) > 0:
        context.bot.send_message(chat_id=update.effective_chat.id, text=response, reply_markup = ReplyKeyboardRemove())

    if shouldSave == True:
        db_saveplayer(user)
    else:
        start(update, context)

    #if user.state >= 7:
    #    return find_friends(user, context, update)
    return DEFAULT

def cancel(update, context):
    return ConversationHandler.END

def on_rules_accepted(update, context):
    user = db_getplayer(update.message.from_user.id)
    if user == None or user.state != 1:
        start(update, context)
        return DEFAULT
    text = update.message.text

    user.state = 2
    response = "Если ты хочешь создать игру, нажми Создать игру. Если у тебя уже есть код приглашения, нажми Присоединиться к игре"

    reply_keyboard = [['Создать игру', 'Присоединиться к игре']]
    reply_markup = ReplyKeyboardMarkup(
        reply_keyboard, one_time_keyboard=True, resize_keyboard=True
    )

    db_saveplayer(user)
    context.bot.send_message(chat_id=update.effective_chat.id, text=response, reply_markup = reply_markup)
    return DEFAULT

def start(update, context):
    if(update.message.chat.username == None):
        print("!! id " + str(update.message.chat) + " -> No username set")
        response = "Пожалуйста, поставьте свое имя пользователя. Это нужно для того, чтобы другие могли с вами познакомиться, после этого обязательно напишите /start"
        context.bot.send_message(chat_id=update.effective_chat.id, text=response)
        context.bot.send_photo(chat_id=update.effective_chat.id, photo=open('1.jpg', 'rb'))
        context.bot.send_photo(chat_id=update.effective_chat.id, photo=open('2.jpg', 'rb'))
        return DEFAULT
    response = "Привет " + update.message.chat.username
    response += "\nКак тебя зовут?"

    user = Player(update.message.from_user.id)
    user.username = update.message.from_user.username
    user.state = 0
    user.game = 0
    user.name = ""
    user.about = ""

    db_saveplayer(user)

    context.bot.send_message(chat_id=update.effective_chat.id, text=response)
    return NAME

def db_getgame(gameId):
    data = g_Conn.execute("SELECT * FROM GAMES WHERE id = ?", (gameId,))
    if data.arraysize == 0:
        return Game(0)
    for row in data:
        pl = Game(row[0])
        pl.state = row[1]
        dc = json.loads(row[2])
        pl.players = []
        for x in dc:
            gp = GamePlayer(0)
            gp.__dict__ = x
            print(gp)
            pl.players.append(gp)
        return pl

def db_delgame(id):
    g_Conn.execute("DELETE FROM GAMES WHERE id = ?", (id,) )
    g_Conn.commit()

def db_savegame(game):
    st = json.dumps(game.players,default=vars)
    if db_getgame(game.id) != None:
        db_delgame(game.id)
    g_Conn.execute("INSERT INTO GAMES VALUES (?,?,?)", (game.id, game.state, st))
    g_Conn.commit()

def db_creategame(creator):
    game = Game(10000 + random.randrange(100000))
    game.state = 0
    game.players = []
    db_savegame(game)
    return game

def db_saveplayer(user):
    if db_getplayer(user.id) != None:
        db_delplayer(user)
    g_Conn.execute("INSERT INTO USERS VALUES (?,?,?,?,?,?)", (user.id, user.username, user.state, user.name, user.about, user.game))
    g_Conn.commit()
def db_delplayer(user):
    g_Conn.execute("DELETE FROM USERS WHERE id = ?", (user.id,) )
    g_Conn.commit()

def db_getAllUsers():
    data = g_Conn.execute("SELECT * FROM USERS")
    lst = data.fetchall()
    return lst

def db_getplayer(user):
    data = g_Conn.execute("SELECT * FROM USERS WHERE id = ?", (user,) )
    if data.arraysize == 0:
        return Player(0)
    for row in data:
        pl = Player(row[0])
        pl.username = row[1]
        pl.state = row[2]
        pl.name = row[3]
        pl.about = row[4]
        pl.game = row[5]
        return pl

def db_create():
    g_Conn.execute("""
            CREATE TABLE GAMES (
                id INTEGER,
                state INTEGER,
                players TEXT
            );
    """)
    g_Conn.execute("""
                CREATE TABLE USERS (
                    id INTEGER,
                    username TEXT,
                    state INTEGER,
                    name TEXT,
                    about TEXT,
                    game INTEGER
                );
        """)
    g_Conn.commit()
def db_exists():
    try:
        data = g_Conn.execute("SELECT * FROM USERS")
    except Exception as e:
        db_create()

DEFAULT, NAME, GAME_RULES, GAME_WAIT = range(4)

if __name__ == '__main__':
    logging.basicConfig(level=logging.WARN,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    global g_Conn
    g_Conn = sqlite3.connect('killer.db', check_same_thread=False)
    db_exists()

    TOKEN = "5611629145:AAFDdxvmIdRWuXl0c8fB0sNaWlR98yVHQco"
    bot = telegram.Bot(token=TOKEN)
    print("Running as " + bot.get_me().username)

    updater = Updater(token=TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    #adm = CommandHandler('sendtoall', sendtoall)

    #dispatcher.add_handler(adm)
    #adm1 = MessageHandler(Filters.forwarded, onFwd)
    #dispatcher.add_handler(adm1)

    conv_handler = ConversationHandler(
        entry_points= [CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(Filters.regex('^(Я согласен)$'), on_rules_accepted)],
            #PHOTO: [MessageHandler(Filters.photo, photo), CommandHandler('skip', skip_photo)],
            #CONFIRM1: [MessageHandler(Filters.regex('^(отлично|изменить)$'), confirm1)],
            #CONFIRM2: [MessageHandler(Filters.regex('^(хочу познакомиться|следующая анкета)$'), confirm2)],
            DEFAULT: [MessageHandler(Filters.text, tg_ontext)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    dispatcher.add_handler(conv_handler)

    cng = MessageHandler(Filters.text, tg_ontext)

    dispatcher.add_handler(cng)

    updater.start_polling()
