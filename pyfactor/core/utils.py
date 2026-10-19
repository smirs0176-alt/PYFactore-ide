"""Мелкие помощники: чтение и запись JSON."""
import json
import os
import tempfile


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data, private=False):
    """Атомарная запись: сначала временный файл рядом, потом замена. Обрыв посреди записи не портит старый файл.

    private=True — права 0600 (для файлов с ключами и токенами; на Windows chmod почти ничего не меняет,
    там защищает профиль пользователя). Возвращает True, если записали."""
    tmp = None
    try:
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=folder)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if private:
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
