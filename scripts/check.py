#!/usr/bin/env python3
"""Проверка проекта: компилирует все .py файлы и ищет синтаксические ошибки.

Запуск:  python scripts/check.py
"""
import os
import py_compile
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bad = 0
total = 0
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for name in files:
        if name.endswith(".py"):
            total += 1
            path = os.path.join(base, name)
            try:
                py_compile.compile(path, doraise=True)
            except py_compile.PyCompileError as e:
                bad += 1
                print("ОШИБКА:", e)
print("Проверено файлов: %d, с ошибками: %d" % (total, bad))
sys.exit(1 if bad else 0)
