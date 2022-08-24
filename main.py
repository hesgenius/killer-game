import telebot, json, os
from telebot import types

try:
    token = "5611629145:AAFDdxvmIdRWuXl0c8fB0sNaWlR98yVHQco"
    bot = telebot.TeleBot(token)
    @bot.message_handler=(commandsa=['/start'])
