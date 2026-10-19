"""Secure storage for credentials on Windows/macOS/Linux.

Strategy:
- Prefer the OS keychain via ``keyring`` when available.
- Fall back to a user-scoped JSON file with 0600 permissions when the keyring is absent.
- Keep secret keys out of the normal app settings file.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from typing import Any, Optional

try:  # pragma: no cover - optional dependency
    import keyring  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    keyring = None

SERVICE_NAME = "PyFactor"
STRICT_ENV = "PYFACTOR_REQUIRE_KEYRING"          # =1: никогда не писать секреты в файл, а явно завершать сохранение ошибкой
_warnings: list = []                              # сообщения для пользователя; забираются через take_warning()
_warned_file = False
DEFAULT_PATH = os.path.join(os.path.expanduser("~"), ".pyfactor", "secrets.json")
LEGACY_SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".pyfactor", "settings.json")


def backend() -> str:
    """'keyring' — секреты в системном хранилище (Windows Credential Manager и т. п.); 'file' — открытый файл secrets.json."""
    return "keyring" if keyring is not None else "file"


def strict() -> bool:
    return os.environ.get(STRICT_ENV, "").strip().lower() in ("1", "true", "yes")


def take_warning() -> str:
    """Возвращает накопленное предупреждение о небезопасном хранении (и очищает его) или пустую строку."""
    msg = "\n\n".join(_warnings)
    _warnings.clear()
    return msg


def _warn_file_fallback(path: str, reason: str) -> None:
    global _warned_file
    if _warned_file:
        return
    _warned_file = True
    _warnings.append("Защищённое хранилище ключей недоступно (%s).\nСекрет сохранён открытым текстом в файле:\n%s\n"
                     "Для Windows Credential Manager установи пакет keyring (pip install keyring). "
                     "Чтобы запретить запись в файл, задай переменную %s=1." % (reason, path, STRICT_ENV))


def _normalize_name(name: str) -> str:
    name = str(name or "").strip()
    if not name:
        raise ValueError("Secret name cannot be empty")
    return name


def _ensure_parent(path: str) -> str:
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    return path


def _load_file(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        return {}
    except Exception:
        pass
    # Файл есть, но не читается: оставляем копию, иначе следующая запись затёрла бы все остальные секреты.
    try:
        if os.path.exists(path) and not os.path.exists(path + ".corrupt"):
            shutil.copy2(path, path + ".corrupt")
    except OSError:
        pass
    return {}


def _fallback_paths(path: Optional[str]) -> list[str]:
    chosen = _ensure_parent(path or DEFAULT_PATH)
    paths = [chosen]
    if path is None and os.path.abspath(chosen) != os.path.abspath(LEGACY_SETTINGS_PATH):
        paths.append(LEGACY_SETTINGS_PATH)
    return paths


def _write_file(path: str, data: dict[str, Any]) -> bool:
    path = _ensure_parent(path)
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".secrets.", suffix=".tmp", dir=os.path.dirname(path))
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
        return True
    except Exception:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return False


def _purge_plaintext(key: str, path: Optional[str]) -> None:
    """Секрет уже в системном хранилище: старые открытые копии в файлах удаляем."""
    for file_path in _fallback_paths(path):
        if not os.path.exists(file_path):
            continue
        data = _load_file(file_path)
        if key in data:
            del data[key]
            _write_file(file_path, data)


def get_secret(name: str, default: Any = "", *, path: Optional[str] = None) -> Any:
    """Return a stored secret or the provided fallback."""
    key = _normalize_name(name)
    if keyring is not None:
        try:
            stored = keyring.get_password(SERVICE_NAME, key)
            if stored is not None:
                return stored
        except Exception:
            pass

    for file_path in _fallback_paths(path):
        data = _load_file(file_path)
        if key in data:
            return data[key]
    return default


def set_secret(name: str, value: Any, *, path: Optional[str] = None) -> bool:
    """Store a secret in the OS keychain when possible, otherwise in a protected JSON file."""
    key = _normalize_name(name)
    payload = "" if value is None else str(value)

    if keyring is not None:
        try:
            keyring.set_password(SERVICE_NAME, key, payload)
            _purge_plaintext(key, path)
            return True
        except Exception:
            pass

    if strict():
        _warnings.append("Секрет не сохранён: системное хранилище недоступно, а режим %s=1 запрещает запись в файл." % STRICT_ENV)
        return False
    file_path = _ensure_parent(path or DEFAULT_PATH)
    _warn_file_fallback(file_path, "пакет keyring не установлен" if keyring is None else "ошибка keyring")
    data = _load_file(file_path)
    data[key] = payload
    persisted = _write_file(file_path, data)
    if path is None and os.path.exists(LEGACY_SETTINGS_PATH):
        legacy = _load_file(LEGACY_SETTINGS_PATH)
        legacy.pop(key, None)
        _write_file(LEGACY_SETTINGS_PATH, legacy)
    return persisted


def delete_secret(name: str, *, path: Optional[str] = None) -> bool:
    """Delete a secret from both keyring and the fallback JSON file."""
    key = _normalize_name(name)
    removed = False
    if keyring is not None:
        try:
            current = keyring.get_password(SERVICE_NAME, key)
            if current is not None:
                keyring.delete_password(SERVICE_NAME, key)
                removed = True
        except Exception:
            pass

    for file_path in _fallback_paths(path):
        data = _load_file(file_path)
        if key in data:
            del data[key]
            removed = _write_file(file_path, data) or removed

    return removed
