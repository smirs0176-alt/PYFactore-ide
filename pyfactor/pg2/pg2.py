"""PG2 — Python 2D engine. Один файл, только стандартная библиотека (tkinter), ничего ставить не нужно.

Приколы из разных движков:
  LÖVE        — свои update(dt) / draw(g) в сцене
  Godot       — сцены, узлы (Node), сигналы on()/emit(), tilemap
  GameMaker   — «будильники»: scene.after(2, fn) и scene.every(1, fn)
  Construct   — поведения: Platform, TopDown, Bullet, Sine, Fade, Wrap, Bounce, Follow
  Phaser      — твины с плавностью (bounce, elastic, back…) и частицы
  Celeste     — «сок»: тряска камеры, hit-stop, койот-тайм, буфер прыжка
  Minecraft   — F3: отладка (FPS, хитбоксы)
  Прочее      — F5 заново · F6 «ЭЛТ» · F7 замедление · P пауза · код Konami · тосты · сохранения

Минимальная игра:
    import pg2
    class Main(pg2.Scene):
        def enter(self):
            self.hero = self.add(pg2.Node(100, 100, 32, 32, "#4a90ff").add(pg2.TopDown()))
    pg2.run(Main, title="Моя игра")
"""
import json
import math
import os
import random
import sys
import threading
import time
import tkinter as tk

__version__ = "1.0"

PALETTE = dict(white="#ffffff", black="#000000", red="#ff5370", green="#7fd962", blue="#4a90ff", yellow="#ffd166",
               orange="#ff9e64", purple="#a78bfa", pink="#ff79c6", gray="#7f8795", cyan="#4dd0e1")


def _rgb(c):
    c = PALETTE.get(c, c).lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(a, b, t):
    """Смешать два цвета: t=0 → a, t=1 → b (так делаем «прозрачность»)."""
    t = max(0.0, min(1.0, t))
    ra, rb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(int(ra[i] + (rb[i] - ra[i]) * t) for i in range(3))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def lerp(a, b, t):
    return a + (b - a) * t


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def _bounce(t):
    if t < 1 / 2.75:
        return 7.5625 * t * t
    if t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + .75
    if t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + .9375
    t -= 2.625 / 2.75
    return 7.5625 * t * t + .984375


EASE = {
    "linear": lambda t: t, "in": lambda t: t * t, "out": lambda t: 1 - (1 - t) ** 2,
    "inout": lambda t: 2 * t * t if t < .5 else 1 - (-2 * t + 2) ** 2 / 2,
    "cubic": lambda t: 1 - (1 - t) ** 3, "bounce": _bounce,
    "elastic": lambda t: 0 if t == 0 else 1 if t == 1 else 2 ** (-10 * t) * math.sin((t * 10 - .75) * (2 * math.pi / 3)) + 1,
    "back": lambda t: 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2,
}


class Graphics:
    """Рисование. g.cam=True — координаты мира (с камерой), False — координаты экрана (интерфейс)."""

    def __init__(self, game):
        self.game, self.c, self.s, self.bg = game, game.canvas, game.scale, game.bg
        self.ox = self.oy = 0.0
        self.cam = True

    def _p(self, x, y):
        return ((x - self.ox) * self.s, (y - self.oy) * self.s) if self.cam else (x * self.s, y * self.s)

    def rect(self, x, y, w, h, color="#ffffff", outline=None, stipple=None):
        x1, y1 = self._p(x, y)
        s = self.s
        kw = {"stipple": stipple} if stipple else {}
        self.c.create_rectangle(x1, y1, x1 + w * s, y1 + h * s, fill=PALETTE.get(color, color) if color else "",
                                outline=outline or "", width=1 if outline else 0, **kw)

    def circle(self, x, y, r, color="#ffffff", outline=None):
        cx, cy = self._p(x, y)
        s = self.s
        self.c.create_oval(cx - r * s, cy - r * s, cx + r * s, cy + r * s, fill=PALETTE.get(color, color) if color else "",
                           outline=outline or "", width=1 if outline else 0)

    def line(self, x1, y1, x2, y2, color="#ffffff", width=1):
        a, b = self._p(x1, y1), self._p(x2, y2)
        self.c.create_line(a[0], a[1], b[0], b[1], fill=PALETTE.get(color, color), width=width * self.s)

    def poly(self, pts, color="#ffffff"):
        flat = [v for p in pts for v in self._p(*p)]
        self.c.create_polygon(flat, fill=PALETTE.get(color, color), outline="")

    def text(self, x, y, s, color="#ffffff", size=14, anchor="nw", bold=False):
        px, py = self._p(x, y)
        self.c.create_text(px, py, text=str(s), fill=PALETTE.get(color, color), anchor=anchor,
                           font=("Segoe UI", -int(size * self.s), "bold" if bold else "normal"))

    def image(self, x, y, img, anchor="nw"):
        px, py = self._p(x, y)
        self.c.create_image(px, py, image=img, anchor=anchor)


class Behavior:
    """Поведение — готовый кусочек логики, который вешается на узел: node.add(Platform())."""

    def start(self, n):
        pass

    def update(self, n, dt):
        pass


class Node:
    """Любой объект игры. x, y — левый верхний угол. Свои классы наследуй от Node и пиши update(dt)."""

    def __init__(self, x=0, y=0, w=16, h=16, color="#ffffff", shape="rect", tags=(), z=0, text="", size=14, image=None, ui=False):
        self.x, self.y, self.w, self.h = float(x), float(y), w, h
        self.vx = self.vy = self.gravity = 0.0
        self.color, self.shape, self.z, self.text, self.size, self.image, self.ui = color, shape, z, text, size, image, ui
        self.tags = {tags} if isinstance(tags, str) else set(tags)
        self.visible = self.alive = True
        self.solid = self.collide_solid = self.on_ground = False
        self.alpha, self.age, self.facing = 1.0, 0.0, 1
        self.scene = self.game = None
        self.behaviors, self._started = [], False

    cx = property(lambda s: s.x + s.w / 2)
    cy = property(lambda s: s.y + s.h / 2)

    def add(self, *behaviors):
        self.behaviors.extend(behaviors)
        return self

    def ready(self):
        """Вызывается один раз перед первым кадром узла."""

    def update(self, dt):
        pass

    def kill(self):
        self.alive = False

    def hits(self, o):
        if self.shape == "circle" and o.shape == "circle":
            return dist(self.cx, self.cy, o.cx, o.cy) < (self.w + o.w) / 2
        return self.x < o.x + o.w and self.x + self.w > o.x and self.y < o.y + o.h and self.y + self.h > o.y

    def draw(self, g):
        col = self.color if self.alpha >= 1 else mix(g.bg, self.color, self.alpha)
        if self.shape == "circle":
            g.circle(self.cx, self.cy, self.w / 2, col)
        elif self.shape == "text":
            g.text(self.x, self.y, self.text, col, self.size)
        elif self.shape == "image" and self.image:
            g.image(self.x, self.y, self.game.image(self.image))
        else:
            g.rect(self.x, self.y, self.w, self.h, col)

    def _step(self, dt):
        if not self._started:
            self._started = True
            for b in self.behaviors:
                b.start(self)
            self.ready()
        self.age += dt
        for b in self.behaviors:
            b.update(self, dt)
        self.update(dt)
        self._move(dt)

    def _move(self, dt):
        self.vy += self.gravity * dt
        dx, dy = self.vx * dt, self.vy * dt
        if not self.collide_solid:
            self.x += dx
            self.y += dy
            return
        solids = [s for s in self.scene._solids if s is not self]
        self.x += dx
        for s in solids:
            if self.hits(s):
                self.x = s.x - self.w if dx > 0 else s.x + s.w
                self.vx = 0
        self.y += dy
        self.on_ground = False
        for s in solids:
            if self.hits(s):
                if dy > 0:
                    self.y, self.on_ground = s.y - self.h, True
                else:
                    self.y = s.y + s.h
                self.vy = 0


class Tile(Node):
    """Блок уровня: тело + светлая полоска сверху."""

    def __init__(self, *a, top=None, **kw):
        super().__init__(*a, **kw)
        self.top = top or mix(self.color, "#ffffff", .12)

    def draw(self, g):
        super().draw(g)
        g.rect(self.x, self.y, self.w, 4, self.top)


class Label(Node):
    """Текст на экране (не двигается с камерой)."""

    def __init__(self, x, y, text="", color="#ffffff", size=16, **kw):
        super().__init__(x, y, 0, 0, color, "text", text=text, size=size, ui=True, z=1000, **kw)


class Particle(Node):
    def __init__(self, x, y, vx, vy, life, size, color, gravity, shape):
        super().__init__(x - size / 2, y - size / 2, size, size, color, shape, z=100)
        self.vx, self.vy, self.gravity, self.life, self.size0 = vx, vy, gravity, life, size

    def update(self, dt):
        k = self.age / self.life
        if k >= 1:
            return self.kill()
        self.alpha = 1 - k
        self.w = self.h = self.size0 * (1 - k * .5)


class Emitter(Node):
    """Постоянный источник частиц: scene.add(Emitter(x, y, rate=30, color=['#f80','#ff0']))."""

    def __init__(self, x, y, rate=30, **burst):
        super().__init__(x, y, 1, 1, shape="rect")
        self.rate, self.burst, self._acc, self.visible = rate, burst, 0.0, False

    def update(self, dt):
        self._acc += self.rate * dt
        while self._acc >= 1:
            self._acc -= 1
            self.scene.burst(self.x, self.y, n=1, **self.burst)


# ---------------------------------------------------------------- поведения
def _held(g, names):
    return any(g.key(k) for k in names)


class Platform(Behavior):
    """Платформер: бег, прыжок, гравитация, койот-тайм и буфер прыжка (как в Celeste)."""

    def __init__(self, speed=190, jump=430, gravity=1300, left=("left", "a"), right=("right", "d"), up=("up", "w", "space")):
        self.speed, self.jump, self.g, self.l, self.r, self.u = speed, jump, gravity, left, right, up

    def start(self, n):
        n.gravity, n.collide_solid = self.g, True
        self.coyote = self.buffer = 0.0

    def update(self, n, dt):
        g = n.game
        ax = _held(g, self.r) - _held(g, self.l)
        n.vx = ax * self.speed
        if ax:
            n.facing = ax
        self.coyote = .1 if n.on_ground else self.coyote - dt
        self.buffer = .1 if any(g.pressed(k) for k in self.u) else self.buffer - dt
        if self.buffer > 0 and self.coyote > 0:
            n.vy, self.buffer, self.coyote = -self.jump, 0, 0
            n.scene.emit("jump", n)
        if n.vy < 0 and not _held(g, self.u):
            n.vy += self.g * dt * 1.5  # отпустил кнопку — прыжок ниже


class TopDown(Behavior):
    """Вид сверху: 8 направлений, по диагонали не быстрее."""

    def __init__(self, speed=200, up=("up", "w"), down=("down", "s"), left=("left", "a"), right=("right", "d")):
        self.speed, self.k = speed, (up, down, left, right)

    def start(self, n):
        n.collide_solid = True

    def update(self, n, dt):
        u, d, l, r = self.k
        g = n.game
        ax, ay = _held(g, r) - _held(g, l), _held(g, d) - _held(g, u)
        k = self.speed / (math.hypot(ax, ay) or 1)
        n.vx, n.vy = ax * k, ay * k
        if ax:
            n.facing = ax


class Bullet(Behavior):
    """Летит по прямой: Bullet(speed=400, angle=-90) (угол в градусах, 0 = вправо), живёт life секунд."""

    def __init__(self, speed=400, angle=0, life=2.0):
        self.speed, self.angle, self.life = speed, angle, life

    def start(self, n):
        a = math.radians(self.angle)
        n.vx, n.vy = math.cos(a) * self.speed, math.sin(a) * self.speed

    def update(self, n, dt):
        if n.age > self.life:
            n.kill()


class Sine(Behavior):
    """Колебание свойства: Sine('y', amp=20, period=1.5) — парящий враг, пульсирующая монета."""

    def __init__(self, prop="y", amp=10, period=1.0):
        self.prop, self.amp, self.period = prop, amp, period

    def start(self, n):
        self.base = getattr(n, self.prop)

    def update(self, n, dt):
        setattr(n, self.prop, self.base + math.sin(n.age * 2 * math.pi / self.period) * self.amp)


class Fade(Behavior):
    """Исчезает за sec секунд и удаляется."""

    def __init__(self, sec=1.0):
        self.sec = sec

    def update(self, n, dt):
        n.alpha = max(0.0, 1 - n.age / self.sec)
        if n.age >= self.sec:
            n.kill()


class Wrap(Behavior):
    """Вылетел за край экрана — появился с другой стороны (Asteroids)."""

    def update(self, n, dt):
        W, H = n.game.w, n.game.h
        n.x = (n.x + n.w) % (W + n.w) - n.w
        n.y = (n.y + n.h) % (H + n.h) - n.h


class Bounce(Behavior):
    """Отскакивает от краёв экрана (Pong, DVD-заставка)."""

    def update(self, n, dt):
        W, H = n.game.w, n.game.h
        if n.x < 0 or n.x + n.w > W:
            n.vx, n.x = -n.vx, clamp(n.x, 0, W - n.w)
        if n.y < 0 or n.y + n.h > H:
            n.vy, n.y = -n.vy, clamp(n.y, 0, H - n.h)


class Follow(Behavior):
    """Гонится за узлом target (или за тегом): Follow('player', speed=90)."""

    def __init__(self, target, speed=90):
        self.target, self.speed = target, speed

    def update(self, n, dt):
        t = self.target if isinstance(self.target, Node) else n.scene.first(self.target)
        if t and t.alive:
            d = dist(n.cx, n.cy, t.cx, t.cy) or 1
            n.vx, n.vy = (t.cx - n.cx) / d * self.speed, (t.cy - n.cy) / d * self.speed


# ---------------------------------------------------------------- камера и сцена
class Camera:
    def __init__(self):
        self.x = self.y = self.ox = self.oy = 0.0
        self.target, self.lerp, self.bounds = None, .12, None
        self._pow = self._t = self._dur = 0.0

    def follow(self, node, lerp=.12, bounds=None):
        self.target, self.lerp = node, lerp
        if bounds:
            self.bounds = bounds

    def shake(self, power=6, t=.25):
        self._pow, self._t, self._dur = power, t, t

    def update(self, dt, W, H):
        if self.target:
            k = 1 - (1 - self.lerp) ** (dt * 60)
            self.x += (self.target.cx - W / 2 - self.x) * k
            self.y += (self.target.cy - H / 2 - self.y) * k
        if self.bounds:
            x0, y0, x1, y1 = self.bounds
            self.x = clamp(self.x, x0, max(x0, x1 - W))
            self.y = clamp(self.y, y0, max(y0, y1 - H))
        if self._t > 0:
            self._t -= dt
            p = self._pow * max(0.0, self._t) / self._dur
            self.ox, self.oy = random.uniform(-p, p), random.uniform(-p, p)
        else:
            self.ox = self.oy = 0.0


class Timer:
    def __init__(self, sec, fn, every):
        self.t = self.sec = sec
        self.fn, self.every, self.alive = fn, every, True

    def cancel(self):
        self.alive = False


class Scene:
    """Экран игры (меню, уровень, game over). Переопредели enter / update / draw."""

    def __init__(self):
        self.nodes, self.game, self.bg = [], None, None
        self.camera = Camera()
        self._timers, self._tweens, self._handlers, self._solids = [], [], {}, []

    # --- твои методы
    def enter(self):
        """Вызывается, когда сцена стала текущей."""

    def exit(self):
        pass

    def update(self, dt):
        pass

    def draw(self, g):
        """Рисование поверх всего (интерфейс). g.cam=False — экранные координаты."""

    # --- узлы
    def add(self, *nodes):
        for n in nodes:
            n.scene, n.game = self, self.game
            self.nodes.append(n)
        return nodes[0] if len(nodes) == 1 else nodes

    def find(self, tag):
        return [n for n in self.nodes if n.alive and tag in n.tags]

    def first(self, tag):
        return next((n for n in self.nodes if n.alive and tag in n.tags), None)

    def solid_at(self, x, y):
        return any(s.x <= x < s.x + s.w and s.y <= y < s.y + s.h for s in self._solids)

    def collide(self, tag_a, tag_b, fn):
        for a in self.find(tag_a):
            for b in self.find(tag_b):
                if a.alive and b.alive and a.hits(b):
                    fn(a, b)

    # --- будильники, твины, сигналы
    def after(self, sec, fn):
        t = Timer(sec, fn, False)
        self._timers.append(t)
        return t

    def every(self, sec, fn):
        t = Timer(sec, fn, True)
        self._timers.append(t)
        return t

    def tween(self, obj, prop, to, sec, ease="out", done=None, delay=0.0):
        tw = dict(o=obj, p=prop, a=getattr(obj, prop), b=to, t=-delay, d=max(sec, 1e-6),
                  e=EASE[ease] if isinstance(ease, str) else ease, done=done)
        self._tweens.append(tw)
        return tw

    def on(self, name, fn):
        self._handlers.setdefault(name, []).append(fn)

    def emit(self, name, *args):
        for fn in list(self._handlers.get(name, [])):
            fn(*args)

    # --- эффекты
    def burst(self, x, y, n=16, color="#ffd166", speed=160, life=.6, size=4, gravity=350, spread=360, angle=-90, shape="rect"):
        cols = color if isinstance(color, (list, tuple)) else [color]
        for _ in range(n):
            a = math.radians(angle + random.uniform(-spread / 2, spread / 2))
            v = speed * random.uniform(.4, 1)
            self.add(Particle(x, y, math.cos(a) * v, math.sin(a) * v, life * random.uniform(.6, 1.2),
                              size * random.uniform(.6, 1.3), random.choice(cols), gravity, shape))

    def popup(self, x, y, text, color="#ffffff", size=14, up=40, sec=.8):
        n = self.add(Node(x, y, 0, 0, color, "text", text=text, size=size, z=200))
        self.tween(n, "y", y - up, sec, "out")
        self.tween(n, "alpha", 0, sec, "in", done=n.kill)
        return n

    def tilemap(self, rows, tile=32, legend=None, x=0, y=0):
        """Уровень из строк. '#' — стена. legend: {символ: {color, solid, tags, factory(x, y)}}"""
        lg = {"#": dict(color="#3b4252", solid=True, tags=("wall",))}
        lg.update(legend or {})
        made = {}
        for r, row in enumerate(rows):
            c = 0
            while c < len(row):
                ch = row[c]
                spec = lg.get(ch)
                if spec is None:
                    c += 1
                    continue
                if callable(spec):
                    spec = dict(factory=spec)
                px, py = x + c * tile, y + r * tile
                if spec.get("factory"):
                    made.setdefault(ch, []).append(self.add(spec["factory"](px, py)))
                    c += 1
                    continue
                run = 1
                while c + run < len(row) and row[c + run] == ch:
                    run += 1
                nd = Tile(px, py, run * tile, tile, spec.get("color", "#3b4252"), tags=spec.get("tags", ()), z=spec.get("z", 0), top=spec.get("top"))
                nd.solid = spec.get("solid", False)
                made.setdefault(ch, []).append(self.add(nd))
                c += run
        W = max((len(r) for r in rows), default=0) * tile
        if self.camera.bounds is None:
            self.camera.bounds = (x, y, x + W, y + len(rows) * tile)
        return made

    # --- внутреннее
    def _tick(self, dt):
        if dt <= 0:
            return
        for t in list(self._timers):
            t.t -= dt
            if t.t <= 0 and t.alive:
                t.fn()
                if t.every and t.alive:
                    t.t += t.sec
                else:
                    t.alive = False
        self._timers = [t for t in self._timers if t.alive]
        for tw in list(self._tweens):
            tw["t"] += dt
            if tw["t"] < 0:
                continue
            k = min(1.0, tw["t"] / tw["d"])
            setattr(tw["o"], tw["p"], tw["a"] + (tw["b"] - tw["a"]) * tw["e"](k))
            if k >= 1:
                self._tweens.remove(tw)
                if tw["done"]:
                    tw["done"]()
        self._solids = [n for n in self.nodes if n.solid and n.alive]
        for n in list(self.nodes):
            if n.alive:
                n._step(dt)
        self.nodes = [n for n in self.nodes if n.alive]
        self.update(dt)
        self.camera.update(dt, self.game.w, self.game.h)

    def _render(self, g):
        cam, W, H = self.camera, self.game.w, self.game.h
        g.ox, g.oy, g.cam = cam.x + cam.ox, cam.y + cam.oy, True
        for n in sorted((n for n in self.nodes if n.visible), key=lambda n: n.z):
            if n.ui:
                g.cam = False
                n.draw(g)
                g.cam = True
            elif n.shape == "text" or not (n.x + n.w < g.ox or n.x > g.ox + W or n.y + n.h < g.oy or n.y > g.oy + H):
                n.draw(g)
        if self.game.debug:
            for n in self.nodes:
                g.rect(n.x, n.y, n.w, n.h, None, outline="#ff5370")
        g.cam = False
        self.draw(g)


# ---------------------------------------------------------------- игра
_KEYS = {"Left": "left", "Right": "right", "Up": "up", "Down": "down", "space": "space", "Return": "enter",
         "Escape": "esc", "Shift_L": "shift", "Shift_R": "shift", "Control_L": "ctrl", "Control_R": "ctrl",
         "Alt_L": "alt", "BackSpace": "backspace", "Tab": "tab"}
_KONAMI = ["up", "up", "down", "down", "left", "right", "left", "right", "b", "a"]


class Game:
    def __init__(self, title="PG2", width=800, height=480, bg="#14161c", fps=60, scale=1):
        self.title, self.w, self.h, self.bg, self.fps, self.scale = title, width, height, bg, fps, scale
        self.root = tk.Tk()
        self.root.title(title)
        self.root.resizable(False, False)
        self.canvas = tk.Canvas(self.root, width=width * scale, height=height * scale, bg=bg, highlightthickness=0)
        self.canvas.pack()
        self.g = Graphics(self)
        self.scene = self._factory = self._trans = self._flash = None
        self._down, self._pressed, self._released, self._rel = set(), set(), set(), {}
        self.mouse, self.mouse_down, self.clicked = (0, 0), False, False
        self.timescale, self._freeze, self.paused, self.debug, self.crt = 1.0, 0.0, False, False, False
        self.hotkeys, self._toasts, self._konami, self._images = True, [], [], {}
        self.frame, self._fps, self._max, self._running = 0, 60.0, None, False
        r = self.root
        r.bind("<KeyPress>", self._kdown)
        r.bind("<KeyRelease>", self._kup)
        r.bind("<Motion>", self._mmove)
        r.bind("<ButtonPress-1>", self._mpress)
        r.bind("<ButtonRelease-1>", lambda e: setattr(self, "mouse_down", False))
        r.protocol("WM_DELETE_WINDOW", self.quit)
        r.focus_force()

    # --- ввод
    def _name(self, e):
        if sys.platform == "win32" and 65 <= e.keycode <= 90:
            return chr(e.keycode).lower()  # WASD работает и на русской раскладке
        return _KEYS.get(e.keysym, e.keysym.lower())

    def _kdown(self, e):
        k = self._name(e)
        job = self._rel.pop(k, None)
        if job:
            self.root.after_cancel(job)  # автоповтор клавиши — не отпускание
        if k not in self._down:
            self._down.add(k)
            self._pressed.add(k)
            self._konami = (self._konami + [k])[-10:]
            if self._konami == _KONAMI:
                self._konami = []
                self.toast("KONAMI! +30 жизней 😎")
                self.flash("#ffd166")
                if self.scene:
                    self.scene.burst(self.w / 2 + self.scene.camera.x, self.h / 2 + self.scene.camera.y, 60,
                                     ["#ff5370", "#ffd166", "#7fd962", "#4a90ff"], 300, 1.2, 5, 200)
                    self.scene.emit("konami")

    def _kup(self, e):
        k = self._name(e)

        def real():
            self._rel.pop(k, None)
            self._down.discard(k)
            self._released.add(k)
        self._rel[k] = self.root.after(12, real)

    def _mmove(self, e):
        self.mouse = (e.x / self.scale, e.y / self.scale)

    def _mpress(self, e):
        self._mmove(e)
        self.mouse_down = self.clicked = True

    def key(self, name):
        """Зажата ли клавиша: 'left', 'a', 'space', 'enter', 'esc'…"""
        return name in self._down

    def pressed(self, name):
        """Нажата именно в этом кадре."""
        return name in self._pressed

    def released(self, name):
        return name in self._released

    def world_mouse(self):
        c = self.scene.camera if self.scene else Camera()
        return self.mouse[0] + c.x, self.mouse[1] + c.y

    # --- сцены
    def go(self, scene, transition="fade", t=.4):
        if isinstance(scene, type):
            self._factory, scene = scene, scene()
        else:
            self._factory = type(scene)
        if self.scene is None or not transition:
            self._switch(scene)
        else:
            self._trans = dict(next=scene, kind=transition, t=0.0, dur=t, phase=0)

    def _switch(self, scene):
        if self.scene:
            self.scene.exit()
        self.scene, scene.game = scene, self
        for n in scene.nodes:
            n.game = self
        scene.enter()

    def restart(self):
        try:
            self.go(self._factory(), "fade", .25)
            self.toast("Перезапуск (F5)")
        except Exception as e:
            self.toast("Перезапуск не вышел: %s" % e)

    # --- «сок»
    def shake(self, power=8, t=.3):
        if self.scene:
            self.scene.camera.shake(power, t)

    def freeze(self, sec=.06):
        """Hit-stop: игра замирает на мгновение при ударе."""
        self._freeze = max(self._freeze, sec)

    def flash(self, color="#ffffff", t=.15):
        self._flash = [color, t, t]

    def toast(self, text, sec=2.2):
        self._toasts.append([str(text), sec, sec])

    def beep(self, freq=440, ms=70):
        try:
            import winsound
            threading.Thread(target=winsound.Beep, args=(int(freq), int(ms)), daemon=True).start()
        except Exception:
            self.root.bell()

    # --- файлы
    def image(self, path, zoom=1):
        key = (path, zoom)
        if key not in self._images:
            img = tk.PhotoImage(file=path)
            z = self.scale * zoom
            self._images[key] = img.zoom(int(z)) if z >= 1 else img
        return self._images[key]

    def _save_path(self, name):
        d = os.path.join(os.path.expanduser("~"), ".pg2", "saves")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "%s_%s.json" % ("".join(c if c.isalnum() else "_" for c in self.title), name))

    def save(self, name, data):
        with open(self._save_path(name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def load(self, name, default=None):
        try:
            with open(self._save_path(name), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    # --- цикл
    def run(self, scene, frames=None):
        self._max, self._running = frames, True
        self.go(scene, None)
        self._last = time.perf_counter()
        self._loop()
        self.root.mainloop()

    def quit(self):
        self._running = False
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _loop(self):
        if not self._running:
            return
        t0 = time.perf_counter()
        dt, self._last = min(t0 - self._last, 1 / 20), t0
        self._frame(dt)
        if self._running:
            self.root.after(max(1, int(1000 / self.fps - (time.perf_counter() - t0) * 1000)), self._loop)

    def _frame(self, dt):
        raw = dt
        self._fps += (1 / max(raw, 1e-6) - self._fps) * .1
        if self.hotkeys:
            for k, fn in (("f3", lambda: setattr(self, "debug", not self.debug)), ("f5", self.restart),
                          ("f6", lambda: setattr(self, "crt", not self.crt)),
                          ("f7", lambda: setattr(self, "timescale", .25 if self.timescale == 1 else 1.0)),
                          ("p", lambda: setattr(self, "paused", not self.paused))):
                if k in self._pressed:
                    fn()
        if self._freeze > 0:
            self._freeze -= raw
            dt = 0
        elif self.paused:
            dt = 0
        else:
            dt *= self.timescale
        tr = self._trans
        if tr:
            tr["t"] += raw
            if tr["t"] >= tr["dur"]:
                if tr["phase"] == 0:
                    self._switch(tr["next"])
                    tr["phase"], tr["t"] = 1, 0.0
                else:
                    self._trans = None
        if self.scene:
            self.scene._tick(dt)
        self._render(raw)
        self._pressed.clear()
        self._released.clear()
        self.clicked = False
        self.frame += 1
        if self._max and self.frame >= self._max:
            self.quit()

    def _render(self, raw):
        c, g, s = self.canvas, self.g, self.scale
        c.delete("all")
        bg = (self.scene.bg if self.scene else None) or self.bg
        c.configure(bg=bg)
        g.bg = bg
        if self.scene:
            self.scene._render(g)
        g.cam = False
        W, H = self.w, self.h
        tr = self._trans
        if tr:
            q = tr["t"] / tr["dur"]
            q = q if tr["phase"] == 0 else 1 - q
            if tr["kind"] == "wipe":
                g.rect(0, 0, W * q, H, "#000000")
            elif tr["kind"] == "iris":
                r = (1 - q) * math.hypot(W, H) / 2
                big = math.hypot(W, H) * 2
                c.create_oval((W / 2 - r - big / 2) * s, (H / 2 - r - big / 2) * s, (W / 2 + r + big / 2) * s,
                              (H / 2 + r + big / 2) * s, outline="#000000", width=big * s)
            elif q > .02:
                g.rect(0, 0, W, H, "#000000", stipple="gray75" if q > .75 else "gray50" if q > .4 else "gray25")
        if self._flash:
            self._flash[1] -= raw
            f = self._flash[1] / self._flash[2]
            if f <= 0:
                self._flash = None
            else:
                g.rect(0, 0, W, H, self._flash[0], stipple="gray75" if f > .6 else "gray50" if f > .3 else "gray25")
        if self.crt:
            for y in range(0, H, 3):
                c.create_line(0, y * s, W * s, y * s, fill="#000000", stipple="gray25")
        for tst in list(self._toasts):
            tst[1] -= raw
            if tst[1] <= 0:
                self._toasts.remove(tst)
        for i, (txt, left, total) in enumerate(self._toasts[-3:][::-1]):
            slide = min(1, left / .25, (total - left) / .25)
            y = H - 40 - i * 34 + (1 - slide) * 30
            w = 14 + len(txt) * 8
            g.rect(W / 2 - w / 2, y, w, 26, "#2a3140", outline="#4a90ff")
            g.text(W / 2, y + 13, txt, "#ffffff", 13, "center")
        if self.paused:
            g.text(W / 2, H / 2, "ПАУЗА  (P)", "#ffffff", 28, "center", True)
        if self.debug:
            n = len(self.scene.nodes) if self.scene else 0
            mx, my = self.world_mouse()
            for i, line in enumerate(("FPS %d" % round(self._fps), "узлов %d" % n, "кадр %d" % self.frame,
                                      "мышь %d, %d" % (mx, my), "x%.2f" % self.timescale)):
                g.text(9, 9 + i * 16, line, "#000000", 13)
                g.text(8, 8 + i * 16, line, "#7fd962", 13)


def run(scene, title="PG2", width=800, height=480, bg="#14161c", fps=60, scale=1):
    """Запустить игру одной строкой: pg2.run(MainScene, title='Игра')."""
    Game(title, width, height, bg, fps, scale).run(scene)
