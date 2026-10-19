"""Пути, цвета, константы и каталог библиотек PyFactor."""
import builtins
import keyword
import os
import subprocess
import sys

HOME = os.path.join(os.path.expanduser("~"), ".pyfactor")
PROJ_ROOT = os.path.join(os.path.expanduser("~"), "PyFactorProjects")
MYCODES = os.path.join(HOME, "mycodes")
GAMES = os.path.join(HOME, "gamecenter")
ACCOUNT_F = os.path.join(HOME, "account.json")
USERS_F = os.path.join(HOME, "users.json")
SETTINGS_F = os.path.join(HOME, "settings.json")
# connect.json кладёт сайт в скачанный архив: рядом с папкой pyfactor. По нему приложение само входит в аккаунт.
def _app_root():
    """Папка приложения. В EXE (onefile) __file__ лежит во временной папке распаковки, а connect.json кладут рядом с PyFactor.exe."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


APP_ROOT = _app_root()
CONNECT_F = os.path.join(APP_ROOT, "connect.json")
for _d in (HOME, PROJ_ROOT, MYCODES, GAMES):
    os.makedirs(_d, exist_ok=True)

PG2_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pg2")  # движок PG2
BG, BG2, BG3 = "#1d2128", "#181b21", "#21262e"
FG, DIM = "#d4d7de", "#7f8795"
ACC, GREEN, RED, YEL, BLUE = "#4a90ff", "#3ddc84", "#ff5370", "#ffcb6b", "#82aaff"
NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

TEXT_EXT = {".py", ".txt", ".md", ".json", ".csv", ".ini", ".cfg", ".yaml", ".yml", ".xml",
            ".html", ".css", ".js", ".toml", ".log", ".bat", ".sh", ".bf", ".ook", ".lol", ".rus", ""}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".svg",
           ".wav", ".mp3", ".ogg", ".flac", ".ttf", ".otf", ".mp4"}
DATA_EXT = {".json", ".txt", ".csv", ".db", ".sqlite", ".md", ".ini", ".cfg", ".yaml", ".yml", ".xml", ".toml"}
WEB_EXT = {".html", ".htm", ".css", ".js", ".mjs"}
FOLDER_ICONS = {"python": "🐍", "web": "🌐", "libraries": "📚", "assets": "🎨", "data": "🗄️", "other": "📦"}

STD = getattr(sys, "stdlib_module_names", frozenset(
    "os sys math random time json re datetime collections itertools functools pathlib threading "
    "subprocess sqlite3 socket tkinter turtle csv hashlib logging argparse urllib unittest decimal "
    "statistics ast queue shutil zipfile base64 copy string struct typing".split()))

# (имя, строка импорта, описание, тип)
LIBS = [
    ("pygame", "import pygame", "Игры: окно, спрайты, звук, управление", "ext"),
    ("tkinter", "import tkinter as tk", "Окна и интерфейсы, встроено в Python", "std"),
    ("turtle", "import turtle", "Рисование черепашкой — для обучения", "std"),
    ("random", "import random", "Случайные числа и выбор", "std"),
    ("math", "import math", "Математика: sin, cos, sqrt, pi", "std"),
    ("time", "import time", "Время, паузы, замеры", "std"),
    ("os", "import os", "Файлы, папки, система", "std"),
    ("sys", "import sys", "Параметры и выход из программы", "std"),
    ("json", "import json", "Сохранение и чтение JSON", "std"),
    ("re", "import re", "Регулярные выражения", "std"),
    ("datetime", "import datetime", "Даты и время", "std"),
    ("collections", "import collections", "deque, Counter, defaultdict", "std"),
    ("itertools", "import itertools", "Мощные итераторы", "std"),
    ("functools", "import functools", "lru_cache, partial и др.", "std"),
    ("pathlib", "from pathlib import Path", "Удобные пути к файлам", "std"),
    ("threading", "import threading", "Потоки", "std"),
    ("subprocess", "import subprocess", "Запуск других программ", "std"),
    ("sqlite3", "import sqlite3", "Встроенная база данных", "std"),
    ("socket", "import socket", "Сеть на низком уровне", "std"),
    ("csv", "import csv", "Таблицы CSV", "std"),
    ("hashlib", "import hashlib", "Хэши: sha256, md5", "std"),
    ("logging", "import logging", "Логи", "std"),
    ("argparse", "import argparse", "Аргументы командной строки", "std"),
    ("urllib", "import urllib.request", "Скачивание по ссылкам", "std"),
    ("unittest", "import unittest", "Тесты", "std"),
    ("statistics", "import statistics", "Среднее, медиана", "std"),
    ("numpy", "import numpy as np", "Быстрые массивы и математика", "ext"),
    ("pandas", "import pandas as pd", "Таблицы и анализ данных", "ext"),
    ("matplotlib", "import matplotlib.pyplot as plt", "Графики", "ext"),
    ("requests", "import requests", "HTTP-запросы", "ext"),
    ("flask", "from flask import Flask", "Простой веб-сервер", "ext"),
    ("django", "import django", "Большой веб-фреймворк", "ext"),
    ("fastapi", "from fastapi import FastAPI", "Современное веб-API", "ext"),
    ("PIL", "from PIL import Image", "Картинки (Pillow)", "ext"),
    ("cv2", "import cv2", "Компьютерное зрение (OpenCV)", "ext"),
    ("scipy", "import scipy", "Научные вычисления", "ext"),
    ("sympy", "import sympy", "Символьная математика", "ext"),
    ("arcade", "import arcade", "Простой 2D игровой движок", "ext"),
    ("pyglet", "import pyglet", "Окна, графика, звук", "ext"),
    ("ursina", "from ursina import *", "3D-игры на Python", "ext"),
    ("kivy", "import kivy", "Мобильные и touch-приложения", "ext"),
    ("bs4", "from bs4 import BeautifulSoup", "Разбор HTML", "ext"),
    ("rich", "from rich import print", "Красивый вывод в консоли", "ext"),
    ("pytest", "import pytest", "Удобные тесты", "ext"),
    ("sqlalchemy", "import sqlalchemy", "Работа с базами через объекты", "ext"),
    ("telebot", "import telebot", "Telegram-боты", "ext"),
    ("discord", "import discord", "Discord-боты", "ext"),
    ("tqdm", "from tqdm import tqdm", "Полоска прогресса для циклов", "ext"),
    ("colorama", "from colorama import Fore, Style", "Цветной текст в консоли", "ext"),
    ("pyttsx3", "import pyttsx3", "Озвучка текста голосом (без интернета)", "ext"),
    ("openpyxl", "import openpyxl", "Чтение и запись Excel-файлов", "ext"),
    # --- Web: подключаются в <head> HTML-файла (в CSS-файле ссылки на стили станут @import)
    ("Bootstrap CSS", '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">',
     "Готовые кнопки, сетка и формы", "web"),
    ("Bootstrap JS", '<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>',
     "Меню, окна и вкладки для Bootstrap", "web"),
    ("Tailwind CSS", '<script src="https://cdn.tailwindcss.com"></script>',
     "Стили прямо в class: text-xl p-4 bg-blue-500", "web"),
    ("jQuery", '<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>',
     "Короткий способ работать со страницей: $(\"p\").hide()", "web"),
    ("Chart.js", '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>',
     "Красивые графики и диаграммы", "web"),
    ("Animate.css", '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css">',
     "Готовые анимации: class=\"animate__bounce\"", "web"),
    ("Font Awesome", '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">',
     "Тысячи иконок", "web"),
    ("Google Fonts: Inter", '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">',
     "Красивый шрифт для сайта", "web"),
    ("p5.js", '<script src="https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.4/p5.min.js"></script>',
     "Рисование и творческое кодирование", "web"),
    ("Three.js", '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>',
     "3D-графика в браузере", "web"),
]


def asset_path(name):
    """Return an asset path in source tree or frozen application bundle."""
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, "assets", name),
        os.path.join(base, "..", "assets", name),
    ]
    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", None) or os.path.dirname(base)
        candidates = [
            os.path.join(bundle_root, "pyfactor", "assets", name),
            os.path.join(bundle_root, "assets", name),
        ] + candidates
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.normpath(candidate)
    return os.path.normpath(candidates[0])


def _alias(line):
    p = line.split()
    if "as" in p:
        return p[-1]
    if p[0] == "from":
        return p[-1]
    return p[1].split(".")[0]


IMPORT_BY_NAME = {_alias(l[1]): l[1] for l in LIBS if "*" not in l[1] and l[3] != "web"}
for _l in LIBS:
    if _l[3] != "web":
        IMPORT_BY_NAME.setdefault(_l[0], _l[1])

KW = set(keyword.kwlist) | {"match", "case"}
BUILTINS = set(dir(builtins))
MONO = "Consolas"


def detect_mono():
    """Подбирает моноширинный шрифт. Вызывать после создания окна Tk."""
    global MONO
    import tkinter.font as tkfont
    fams = set(tkfont.families())
    for f in ("Consolas", "Menlo", "DejaVu Sans Mono", "Liberation Mono", "Courier New"):
        if f in fams:
            MONO = f
            break


# Client ID для входа через Google. Это публичный идентификатор, его можно хранить в коде.
# Client Secret в код НЕ вписывается: вводится в ⚙ → «Ключи входа» и хранится только на компьютере.
DEFAULT_GOOGLE_CLIENT_ID = "132220028372-51ptgroap86aofjinnivoqijutnssva8.apps.googleusercontent.com"
