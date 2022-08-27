import datetime
import random
from datetime import timezone
from fuzzywuzzy import fuzz

import telegram.ext
import logging
import sqlite3
import string
import json

from telegram import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, \
    ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, Filters, MessageHandler, ConversationHandler
class Player(object):
    def __init__(self, id):
        self.id = id
    def asString(self):
        return "@" + self.username + " (" + self.name + ")"

class GamePlayer:
    def __init__(self, ply):
        self.ply = ply
        self.dead = False
        self.ingame = True
        self.admin = False
        self.secret = ""

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True)
    def getDefaultString(self, game):
        if not self.admin:
            rs = ""
            if not game.is_started():
                rs += "Ждем начала игры..Только создатель комнаты может ее начать. "
            return rs + "/rules - правила, /help - список доступных команд"
        return "/game_start - начать игру, /help - список команд, всего в игре " + str(len(game.players)) + " игроков."

    def getNextTarget(self, game):
        cur = game.maps[str(self.ply.id)]
        while cur > 0 and cur != self.ply.id:
            pl = None
            for x in game.players:
                if x.ply.id == cur:
                    pl = x
                    break
            if pl is None:
                return None
            if not pl.dead:
                return pl
            cur = game.maps[str(cur)]
        return None

    def handleCommand(self, cmd, game):
        if cmd == '/help':
            res = "Список доступных команд: \n"
            res += "/rules - правила\n"
            res += "/quit - выйти из комнаты\n"
            res += "/secret - посмотреть свое кодовое слово\n"

            if self.admin:
                res += "/game_start - начать игру [admin]\n"
                #res += "/kick - кикнуть игрока [admin]\n"
            return res
        elif cmd == '/rules':
            res = get_rules()
            return res
        elif cmd == '/quit':
            game.pl_quit(self.ply)
            game.check_end()
            if game.is_started():
                pr = None
                for x in game.maps:
                    if game.maps[x] == self.ply.id:
                        pr = x
                game.player_msg(pr, "Ваша цель вышла из игры. Посмотрите /secret")
            db_savegame(game)
            return "Вы вышли из игры."
        elif cmd == '/game_start':
            if not self.admin:
                return "Данная команда доступна только администраторам"
            if game.is_started():
                return "Игра уже запущена!"
            result = game.start_game()
            if result != None:
                return result
            db_savegame(game)
            return ""
        elif cmd == '/secret':
            if not game.is_started():
                return "Игра еще не началась.."
            if self.dead:
                return "Увы, вас убили.."
            rs = "Ваше кодовое слово: ||" + self.secret + "||"
            trg = self.getNextTarget(game)
            if trg is not None:
                rs += " Ваша цель: ||" + trg.ply.asString() + "||"
            return rs
        elif game.is_started():
            for x in game.players:
                if x.secret.lower() == cmd.lower():
                    if self.dead or not self.ingame:
                        return "Вы умерли :("
                    if x.ply.id == self.ply.id:
                        return "Нельзя убить самого себя :("
                    if x.dead or not x.ingame:
                        return "Данный человек уже мертв"
                    if self.getNextTarget(game).ply.id != x.ply.id:
                        return "Это не ваша цель...ватафак"

                    x.dead = True
                    game.player_msg(x.ply.id, "Вас убили :(")
                    game.check_end()
                    db_savegame(game)
                    return "Красава, ты убил " + x.ply.asString() + "."



        return None

def get_rules():
    with open('rules.txt',encoding='utf8') as file:
        return file.read()

class Game(object):
    def __init__(self, id):
        self.id = id
        self.players = []
        self.maps = {}
    def try_join(self, pll):
        gp = GamePlayer(pll)
        if len(self.players) == 0:
            gp.admin = True
        else:
            self.admin_msg("Игрок " + pll.asString() + " зашел в игру")
        pll.game = self.id
        self.players.append(gp)
        db_savegame(self)
        db_saveplayer(pll)
    def is_started(self):
        return len(self.maps) > 0
    def get_gp(self, pll):
        for xx in self.players:
            if xx.ply.id == pll.id:
                return xx
    def admin_msg(self, msg):
        for xx in self.players:
            if xx.admin and xx.ingame:
                g_Bot.send_message(chat_id=xx.ply.id, text=msg)
                return None
    def player_msg(self, userId, msg):
        g_Bot.send_message(chat_id=userId, text=msg)
    def all_msg(self, msg):
        for xx in self.players:
            if xx.ingame:
                self.player_msg(xx.ply.id, msg)

    def kickall(self, msg):
        for xx in self.players:
            if xx.ingame:
                self.player_msg(xx.ply.id, "Вы вышли из лобби (" + msg + ")")
                self.pl_quit(xx.ply)

    def check_end(self):
        if not self.is_started():
            return None
        pl = []
        for x in self.players:
            if not x.dead:
                pl.append(x)
        if len(pl) < 2:
            if len(pl) == 1:
                self.all_msg("Игра окончена! Победитель: " + pl[0].ply.asString())
            self.maps = {}
            self.kickall("Игра окончена")

    def pl_quit(self, pll):
        wasAdmin = False
        for xx in self.players:
            if xx.ingame and xx.ply.id == pll.id:
                wasAdmin = xx.admin
                xx.ingame = False
                if not wasAdmin and not self.is_started():
                    del self.players[self.players.index(xx)]
                    self.admin_msg("Игрок " + pll.asString() + " вышел из игры")
                elif not xx.dead:
                    self.admin_msg("Игрок " + pll.asString() + " вышел из игры")
                    xx.dead = True
                usr = db_getplayer(pll.id)
                pll.game = usr.game = 0
                db_saveplayer(usr)
                db_savegame(self)
                send_lobby(usr.id)
                break
        if wasAdmin:
            self.kickall("Создатель вышел из комнаты")

    def start_game(self):
        if len(self.players) < 2:
            return "Недостаточно игроков: " + str(len(self.players)) + "/2"

        self.all_msg("Игра была начата! Всего играет " + str(len(self.players)) + " игроков. Напоминание: чтобы убить человека вы должны просто отправить его кодовое слово")
        curPly = self.players[0].ply.id
        while len(self.maps) < len(self.players):
            pp = []
            for x in self.players:
                if x.ply.id not in self.maps and curPly != x.ply.id:
                    pp.append(x)
            next = self.players[0]
            if len(pp) > 0:
                next = random.choice(pp)
            self.player_msg(curPly, "Ваша цель: " + next.ply.asString() + ". Никому не говорите об этом!")
            self.maps[curPly] = next.ply.id
            curPly = next.ply.id

            secret = ''.join(random.choice(string.ascii_uppercase) for i in range(3)) + ''.join(random.choice(string.digits) for i in range(4))
            next.secret = secret
        return None




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
    print("Update state" + str(user.state))
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
        context.bot.send_message(chat_id=update.effective_chat.id, text=response)
        context.bot.send_message(chat_id=update.effective_chat.id, text=get_rules(), reply_markup=reply_markup)
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
            send_lobby(update.message.from_user.id)
            return DEFAULT
    elif user.state == 3:
        failJoinMsg = None
        if not update.message.text.isdigit():
            failJoinMsg = "Неверный ввод ID"
        else:
            it = db_getgame(int(update.message.text))
            if it == None or it.id == 0 or len(it.players) == 0:
                failJoinMsg = "Такой игры не существует"
            elif it.is_started():
                failJoinMsg = "Игра уже началась.."
            elif it.get_gp(user) != None:
                failJoinMsg = "Вы уже тут были..."
        if failJoinMsg != None:
            context.bot.send_message(chat_id=update.effective_chat.id, text=failJoinMsg)
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
        if user.game == 0 or game_player == None or not game_player.ingame:
            send_lobby(user.id)
            return tg_ontext(update, context)

        cmd = game_player.handleCommand(update.message.text, gm)
        if cmd == None:
            cmd = game_player.getDefaultString(gm)
        if len(cmd) > 0:
            if cmd.find("||") >= 0:
                context.bot.send_message(chat_id=update.effective_chat.id, text=cmd.replace("-", "\-").replace(")", "\)").replace("(", "\("), parse_mode="MarkdownV2")
            else:
                context.bot.send_message(chat_id=update.effective_chat.id, text=cmd)
        return DEFAULT


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

def send_lobby(userId):
    user = db_getplayer(userId)
    user.state = 2
    user.game = 0
    response = "Если ты хочешь создать игру, нажми Создать игру. Если у тебя уже есть код приглашения, нажми Присоединиться к игре"

    reply_keyboard = [['Создать игру', 'Присоединиться к игре']]
    reply_markup = ReplyKeyboardMarkup(
        reply_keyboard, one_time_keyboard=True, resize_keyboard=True
    )

    db_saveplayer(user)
    g_Bot.send_message(chat_id=userId, text=response, reply_markup=reply_markup)

def on_rules_accepted(update, context):
    user = db_getplayer(update.message.from_user.id)
    if user == None or user.state != 1:
        start(update, context)
        return DEFAULT
    send_lobby(update.message.from_user.id)
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
            p2 = Player(0)
            p2.__dict__ = x["ply"]
            gp.__dict__ = x
            gp.ply = p2
            pl.players.append(gp)
        pl.maps = json.loads(row[3])
        return pl

def db_delgame(id):
    g_Conn.execute("DELETE FROM GAMES WHERE id = ?", (id,) )
    g_Conn.commit()

def db_savegame(game):
    st = json.dumps(game.players,default=vars)
    if db_getgame(game.id) != None:
        db_delgame(game.id)
    g_Conn.execute("INSERT INTO GAMES VALUES (?,?,?,?)", (game.id, game.state, st, json.dumps(game.maps)))
    g_Conn.commit()

def db_creategame(creator):
    newId = 100000 + random.randrange(1000000)
    while db_getgame(newId) != None:
        newId = 10000 + random.randrange(100000)
    game = Game(newId)
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
                players TEXT,
                maps TEXT
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
g_Bot = None
if __name__ == '__main__':
    logging.basicConfig(level=logging.WARN,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    global g_Conn
    g_Conn = sqlite3.connect('killer.db', check_same_thread=False)
    db_exists()

    TOKEN = "5611629145:AAFDdxvmIdRWuXl0c8fB0sNaWlR98yVHQco"
    bot = telegram.Bot(token=TOKEN)
    g_Bot = bot
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

