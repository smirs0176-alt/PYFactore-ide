import json
import os
import tempfile

from pyfactor import config
from pyfactor.core.appengine import AppBundle, AppEngine


def test_app_bundle_registration_and_runtime_metadata():
    with tempfile.TemporaryDirectory() as root:
        engine = AppEngine(root)
        app_dir = os.path.join(root, "demo_app")
        os.makedirs(app_dir, exist_ok=True)
        with open(os.path.join(app_dir, "main.py"), "w", encoding="utf-8") as f:
            f.write("print('hello from app')\n")
        manifest = {
            "title": "Demo App",
            "description": "A tiny demo",
            "author": "Tester",
            "version": "1.0.0",
            "entry": "main.py",
        }
        with open(os.path.join(app_dir, "app.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)

        bundle = engine.register_app(app_dir)
        assert isinstance(bundle, AppBundle)
        assert bundle.title == "Demo App"
        assert bundle.entry.endswith("main.py")
        data = engine.get_app(bundle.app_id)
        assert data is not None
        assert data["title"] == "Demo App"
        assert bundle.runtime["app_id"] == bundle.app_id
        assert bundle.runtime["entry"] == "main.py"


def test_app_engine_can_list_and_import_apps():
    with tempfile.TemporaryDirectory() as root:
        engine = AppEngine(root)
        app_dir = os.path.join(root, "imported_app")
        os.makedirs(app_dir, exist_ok=True)
        with open(os.path.join(app_dir, "main.py"), "w", encoding="utf-8") as f:
            f.write("print('imported')\n")
        with open(os.path.join(app_dir, "app.json"), "w", encoding="utf-8") as f:
            json.dump({"title": "Imported App", "description": "Imported", "entry": "main.py"}, f)

        bundle = engine.register_app(app_dir)
        apps = engine.list_apps()
        assert len(apps) == 1
        assert apps[0]["app_id"] == bundle.app_id
        assert engine.get_app(bundle.app_id)["title"] == "Imported App"
        assert engine.has_app(bundle.app_id)


def test_app_engine_uses_app_icon_when_present():
    with tempfile.TemporaryDirectory() as root:
        engine = AppEngine(root)
        app_dir = os.path.join(root, "icon_app")
        os.makedirs(app_dir, exist_ok=True)
        with open(os.path.join(app_dir, "main.py"), "w", encoding="utf-8") as f:
            f.write("print('with icon')\n")
        with open(os.path.join(app_dir, "icon.png"), "wb") as f:
            f.write(b"fake-png-data")
        with open(os.path.join(app_dir, "app.json"), "w", encoding="utf-8") as f:
            json.dump({"title": "Icon App", "description": "Has icon", "entry": "main.py"}, f)

        bundle = engine.register_app(app_dir)
        assert bundle.icon.endswith("icon.png")
        assert engine.get_app(bundle.app_id)["icon"].endswith("icon.png")


def test_app_engine_rejects_missing_entry_file():
    with tempfile.TemporaryDirectory() as root:
        engine = AppEngine(root)
        app_dir = os.path.join(root, "broken_app")
        os.makedirs(app_dir, exist_ok=True)
        with open(os.path.join(app_dir, "app.json"), "w", encoding="utf-8") as f:
            json.dump({"title": "Broken", "description": "Missing entry", "entry": "missing.py"}, f)

        try:
            engine.register_app(app_dir)
            assert False, "Expected ValueError for missing entry file"
        except ValueError:
            pass

        assert engine.list_apps() == []
        assert engine.get_app("broken_app") is None


def test_asset_path_resolves_bundle_and_source_locations():
    source_path = config.asset_path("icon.png")
    assert os.path.isfile(source_path), source_path
    assert source_path.endswith(os.path.join("pyfactor", "assets", "icon.png")) or source_path.endswith(os.path.join("assets", "icon.png"))

    bundle_root = tempfile.mkdtemp()
    bundle_assets = os.path.join(bundle_root, "pyfactor", "assets")
    os.makedirs(bundle_assets, exist_ok=True)
    with open(os.path.join(bundle_assets, "icon.png"), "wb") as fh:
        fh.write(b"img")

    old_frozen = getattr(__import__("sys"), "frozen", False)
    old_meipass = getattr(__import__("sys"), "_MEIPASS", None)
    import sys
    sys.frozen = True
    sys._MEIPASS = bundle_root
    try:
        bundle_path = config.asset_path("icon.png")
        assert bundle_path == os.path.join(bundle_root, "pyfactor", "assets", "icon.png")
    finally:
        if old_frozen is False:
            sys.frozen = False
        else:
            sys.frozen = old_frozen
        if old_meipass is None:
            delattr(sys, "_MEIPASS")
        else:
            sys._MEIPASS = old_meipass
