"""Безопасная работа с путями: имя файла из диалога не должно выводить за пределы папки проекта."""
import os


class UnsafePath(ValueError):
    pass


def safe_name(name):
    """Имя одного файла или папки: без разделителей, «..», пустых и служебных значений."""
    name = (name or "").strip()
    if not name or name in (".", "..") or "\0" in name:
        raise UnsafePath("Недопустимое имя")
    if "/" in name or "\\" in name or os.path.isabs(name) or (len(name) > 1 and name[1] == ":"):
        raise UnsafePath("В имени нельзя использовать / \\ и диск (например C:)")
    return name


def is_within(base, path):
    """True, если path лежит внутри base (после раскрытия символьных ссылок)."""
    base, path = os.path.realpath(base), os.path.realpath(path)
    try:
        return os.path.commonpath([base, path]) == base
    except ValueError:                       # разные диски в Windows
        return False


def safe_join(base, rel):
    """Склеивает base и относительный путь (подпапки допустимы). Выход за пределы base — UnsafePath."""
    rel = (rel or "").strip()
    if not rel or "\0" in rel or os.path.isabs(rel) or (len(rel) > 1 and rel[1] == ":"):
        raise UnsafePath("Нужен относительный путь внутри проекта")
    p = os.path.normpath(os.path.join(base, rel))
    if not is_within(base, p) or os.path.realpath(p) == os.path.realpath(base):
        raise UnsafePath("Путь выходит за пределы папки проекта")
    return p
