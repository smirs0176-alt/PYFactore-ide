"""Статическая проверка сборки EXE (саму сборку проверяет только Windows-задание CI)."""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _build():
    spec = importlib.util.spec_from_file_location("build_exe", os.path.join(ROOT, "scripts", "build_exe.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_build_command_bundles_dynamic_deps_and_runtime_files():
    m = _build()
    cmd = m.build_command("python", have=lambda mod: True)
    joined = " ".join(cmd)
    assert "--windowed" in cmd and "--onefile" in cmd
    assert "keyring.backends" in joined and "--copy-metadata" in cmd and "pygments.lexers" in joined
    assert any(c.endswith("pyfactor/assets") for c in cmd)
    assert any(c.endswith("pyfactor/pg2") for c in cmd) and any(c.endswith("pyfactor/core/languages") for c in cmd)
    for p in (m.ICON, m.ENTRY, m.PG2_DIR, m.FUNRUN):
        assert os.path.exists(str(p))


def test_build_does_not_require_optional_packages():
    cmd = _build().build_command("python", have=lambda mod: False)
    assert "--copy-metadata" not in cmd and not any("keyring" in c or "pygments" in c for c in cmd)


def test_spec_has_no_machine_specific_paths_and_compiles():
    src = open(os.path.join(ROOT, "PyFactor.spec"), encoding="utf-8").read()
    assert "C:/Users" not in src and "Desktop" not in src
    assert "pg2" in src and "funrun.py" in src
    compile(src, "PyFactor.spec", "exec")
