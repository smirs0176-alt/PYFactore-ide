"""Подсветка весёлых языков: Brainfuck, Ook!, LOLCODE, Русский Питон."""
import re

from pyfactor.core.languages.funrun import RUS
from pyfactor.core.languages.packs import PACKS, spans_pack

LOL_KW = set("""HAI KTHXBYE VISIBLE GIMMEH I HAS A ITZ R SUM DIFF PRODUKT QUOSHUNT MOD BIGGR SMALLR OF AN BOTH EITHER
SAEM DIFFRINT NOT SMOOSH O RLY? YA RLY NO WAI OIC IM IN YR OUTTA UPPIN NERFIN TIL WILE GTFO WIN FAIL NOOB""".split())
BF = re.compile(r"(?P<kw>[<>]+)|(?P<number>[+\-]+)|(?P<func>[\[\]]+)|(?P<string>[.,]+)|(?P<comment>[^<>+\-\[\].,]+)")
LOL = re.compile(r'(?P<comment>BTW.*)|(?P<string>"(?:[^"]|:")*")|(?P<number>-?\d+\.?\d*)|(?P<word>[A-Z?]+)')
RU = re.compile(r'(?P<comment>#.*)|(?P<string>"[^"\n]*"|\'[^\'\n]*\')|(?P<number>\d+\.?\d*)|(?P<word>[A-Za-zА-Яа-яЁё_]\w*)')
RUS_BI = {"вывод", "ввод", "диапазон", "длина", "целое", "строка", "дробное", "список", "словарь", "открыть", "сумма", "макс", "мин"}


def spans_fun(code, lang):
    out = []
    if lang in PACKS:
        return spans_pack(code, PACKS[lang])
    if lang == "bf":
        out = [(m.start(), m.end(), m.lastgroup) for m in BF.finditer(code)]
    elif lang == "ook":
        out = [(m.start(), m.end(), "kw") for m in re.finditer(r"Ook[.?!]", code)]
    elif lang == "lol":
        for m in LOL.finditer(code):
            k = m.lastgroup
            if k != "word":
                out.append((m.start(), m.end(), k))
            elif m.group() in LOL_KW:
                out.append((m.start(), m.end(), "kw"))
    elif lang == "rus":
        for m in RU.finditer(code):
            k, w = m.lastgroup, m.group()
            if k != "word":
                out.append((m.start(), m.end(), k))
            elif w in RUS:
                out.append((m.start(), m.end(), "bi" if w in RUS_BI else "kw"))
    return out
