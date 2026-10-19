"""Шаблоны игр на движке PG2 (создаются через «Новый файл»)."""

PLATFORMER = '''"""Платформер на PG2.
Стрелки / A D — бег · пробел / W — прыжок · F3 — отладка · F5 — заново · P — пауза · F6 — «ЭЛТ» · F7 — замедление
Собери монеты, прыгай на врагов сверху, добеги до флага."""
import random

import pg2

TILE = 32
LEVEL = [
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "                     c c c",
    "               cc   #########",
    "              ####",
    "        ####                    E",
    "  P   ##                    ############          c       G",
    "###############   ##########              ###########   ######",
    "###############   ##########              ###########   ######",
]
W = max(len(r) for r in LEVEL)
LEVEL = [r.ljust(W) for r in LEVEL]


class Player(pg2.Node):
    def __init__(self, x, y):
        super().__init__(x + 4, y + 4, 24, 28, "#4a90ff", tags="player", z=10)
        self.add(pg2.Platform(speed=190, jump=440))
        self.dead = False

    def update(self, dt):
        if self.dead:
            self.vx = self.vy = self.gravity = 0
        else:
            self.gravity = 1300

    def draw(self, g):
        super().draw(g)
        eye = self.x + (15 if self.facing > 0 else 3)
        g.rect(eye, self.y + 7, 6, 6, "#ffffff")
        g.rect(eye + (2 if self.facing > 0 else 0), self.y + 9, 3, 3, "#14161c")


class Coin(pg2.Node):
    def __init__(self, x, y):
        super().__init__(x + 8, y + 8, 16, 16, "#ffd166", "circle", tags="coin", z=3)
        self.add(pg2.Sine("y", amp=4, period=1.2))


class Enemy(pg2.Node):
    def __init__(self, x, y):
        super().__init__(x + 3, y + 6, 26, 26, "#ff5370", tags="enemy", z=5)
        self.gravity, self.collide_solid, self.dir = 1300, True, -1

    def update(self, dt):
        ahead = self.cx + self.dir * (self.w / 2 + 3)
        if not self.scene.solid_at(ahead, self.y + self.h + 4) or self.scene.solid_at(ahead, self.cy):
            self.dir = -self.dir
        self.vx = self.dir * 60

    def draw(self, g):
        super().draw(g)
        g.rect(self.x + 4, self.y + 7, 7, 5, "#ffffff")
        g.rect(self.x + 15, self.y + 7, 7, 5, "#ffffff")
        g.rect(self.x + 7, self.y + 9, 3, 3, "#14161c")
        g.rect(self.x + 16, self.y + 9, 3, 3, "#14161c")


class Flag(pg2.Node):
    def __init__(self, x, y):
        super().__init__(x + 13, y - 32, 6, 64, "#cfd8e3", tags="flag", z=2)

    def draw(self, g):
        super().draw(g)
        g.poly([(self.x + 6, self.y + 2), (self.x + 34, self.y + 14), (self.x + 6, self.y + 26)], "#7fd962")


class Level(pg2.Scene):
    def enter(self):
        self.bg = "#1b2230"
        self.score, self.won = 0, False
        for _ in range(90):
            self.add(pg2.Node(random.randint(0, W * TILE), random.randint(0, 400), 2, 2, "#4b556b", z=-5))
        made = self.tilemap(LEVEL, TILE, {
            "#": dict(color="#3b4252", solid=True, tags="wall"),
            "c": Coin, "E": Enemy, "G": Flag, "P": Player,
        })
        self.player, self.flag = made["P"][0], made["G"][0]
        self.spawn = (self.player.x, self.player.y)
        self.coins_total = len(made["c"])
        self.camera.follow(self.player, 0.1)
        self.hud = self.add(pg2.Label(14, 10, "", "#ffffff", 18))
        hint = self.add(pg2.Label(14, 40, "← → бег · пробел прыжок · прыгай на врагов", "#9aa5b5", 14))
        self.after(5, lambda: self.tween(hint, "alpha", 0, 1))
        self.on("jump", lambda n: self.burst(n.cx, n.y + n.h, 6, "#9aa5b5", 60, .3, 3, 100, 120, 90))

    def update(self, dt):
        p = self.player
        self.collide("player", "coin", self.take)
        self.collide("player", "enemy", self.touch)
        if p.y > self.camera.bounds[3] + 80:
            self.die()
        if not self.won and not p.dead and p.hits(self.flag):
            self.won = True
            self.burst(self.flag.cx, self.flag.y, 70, ["#7fd962", "#ffd166", "#4a90ff", "#ff5370"], 320, 1.4, 5, 260)
            self.game.beep(1046, 200)
        if self.won and self.game.pressed("enter"):
            self.game.restart()
        left = len(self.find("coin"))
        self.hud.text = "Монеты: %d/%d    Очки: %d" % (self.coins_total - left, self.coins_total, self.score)

    def take(self, p, c):
        c.kill()
        self.score += 10
        self.burst(c.cx, c.cy, 12, ["#ffd166", "#ffe9a8"], 140, .5, 4, 200)
        self.popup(c.x, c.y - 6, "+10", "#ffd166")
        self.game.beep(880, 40)
        if not self.find("coin"):
            self.game.toast("Все монеты собраны!")

    def touch(self, p, e):
        if p.dead:
            return
        if p.vy > 0 and p.y + p.h - e.y < 18:
            e.kill()
            p.vy = -320
            self.score += 50
            self.burst(e.cx, e.cy, 18, ["#ff5370", "#ff9e64"], 200, .5, 4, 300)
            self.popup(e.x, e.y - 8, "+50", "#ff9e64")
            self.game.freeze(.05)
            self.game.beep(520, 60)
        else:
            self.die()

    def die(self):
        p = self.player
        if p.dead:
            return
        p.dead, p.visible = True, False
        self.burst(p.cx, p.cy, 30, ["#4a90ff", "#ffffff"], 240, .7, 5, 300)
        self.game.shake(10, .4)
        self.game.flash("#ff5370")
        self.game.beep(180, 150)
        self.after(.7, self.respawn)

    def respawn(self):
        p = self.player
        p.x, p.y = self.spawn
        p.vx = p.vy = 0
        p.dead, p.visible = False, True

    def draw(self, g):
        if self.won:
            g.text(self.game.w / 2, self.game.h / 2 - 30, "ПОБЕДА!", "#7fd962", 48, "center", True)
            g.text(self.game.w / 2, self.game.h / 2 + 20, "очки: %d   ·   Enter — ещё раз" % self.score, "#ffffff", 18, "center")


if __name__ == "__main__":
    pg2.run(Level, title="Платформер PG2")
'''

SHOOTER = '''"""Шутер сверху на PG2.
WASD / стрелки — двигаться · мышь — целиться · клик или пробел — стрелять · F3 — отладка · Enter — заново"""
import math
import random

import pg2


class Ship(pg2.Node):
    def __init__(self, x, y):
        super().__init__(x, y, 26, 26, "#4a90ff", "circle", tags="player", z=10)
        self.add(pg2.TopDown(speed=230))
        self.hp, self.cool, self.angle = 5, 0.0, 0.0

    def update(self, dt):
        mx, my = self.game.mouse
        self.angle = math.atan2(my - self.cy, mx - self.cx)
        self.cool -= dt
        self.x = pg2.clamp(self.x, 0, self.game.w - self.w)
        self.y = pg2.clamp(self.y, 0, self.game.h - self.h)

    def draw(self, g):
        super().draw(g)
        g.line(self.cx, self.cy, self.cx + math.cos(self.angle) * 26, self.cy + math.sin(self.angle) * 26, "#ffffff", 4)


class Main(pg2.Scene):
    def enter(self):
        self.bg = "#10131a"
        self.score, self.over = 0, False
        self.ship = self.add(Ship(387, 227))
        self.hud = self.add(pg2.Label(14, 10, "", "#ffffff", 18))
        self.every(.8, self.spawn)
        self.on("konami", lambda: setattr(self.ship, "hp", 99))

    def spawn(self):
        if self.over:
            return
        W, H = self.game.w, self.game.h
        side = random.choice("lrtb")
        x = {"l": -30, "r": W + 30}.get(side, random.randint(0, W))
        y = {"t": -30, "b": H + 30}.get(side, random.randint(0, H))
        e = pg2.Node(x, y, 24, 24, random.choice(["#ff5370", "#ff9e64", "#c792ea"]), "circle", tags="enemy", z=5)
        self.add(e.add(pg2.Follow("player", random.randint(60, 110))))

    def update(self, dt):
        s, g = self.ship, self.game
        if self.over:
            if g.pressed("enter"):
                g.restart()
            return
        if (g.mouse_down or g.key("space")) and s.cool <= 0:
            s.cool = .16
            a = s.angle
            b = pg2.Node(s.cx - 4, s.cy - 4, 8, 8, "#ffd166", "circle", tags="bullet", z=6)
            self.add(b.add(pg2.Bullet(560, math.degrees(a), 1.2)))
            g.beep(700, 20)
        self.collide("bullet", "enemy", self.shot)
        self.collide("player", "enemy", self.hurt)
        self.hud.text = "Очки: %d     Жизни: %d" % (self.score, max(s.hp, 0))

    def shot(self, b, e):
        b.kill()
        e.kill()
        self.score += 10
        self.burst(e.cx, e.cy, 14, [e.color, "#ffffff"], 220, .5, 4, 0)
        self.game.shake(3, .1)
        self.game.freeze(.02)

    def hurt(self, s, e):
        e.kill()
        s.hp -= 1
        self.burst(s.cx, s.cy, 20, ["#4a90ff", "#ffffff"], 260, .6, 4, 0)
        self.game.shake(9, .3)
        self.game.flash("#ff5370")
        self.game.beep(160, 120)
        if s.hp <= 0:
            self.over = True
            s.visible = False

    def draw(self, g):
        if self.over:
            g.text(self.game.w / 2, self.game.h / 2 - 30, "КОНЕЦ", "#ff5370", 48, "center", True)
            g.text(self.game.w / 2, self.game.h / 2 + 20, "очки: %d   ·   Enter — заново" % self.score, "#ffffff", 18, "center")


if __name__ == "__main__":
    pg2.run(Main, title="Шутер PG2")
'''

BLANK = '''"""Пустая игра на PG2 — отсюда можно начинать.
Стрелки / WASD — двигать квадрат · клик мышью — салют · F3 — отладка · F5 — заново · P — пауза"""
import pg2


class Main(pg2.Scene):
    def enter(self):
        self.hero = self.add(pg2.Node(380, 220, 40, 40, "#4a90ff").add(pg2.TopDown(speed=240)))
        self.label = self.add(pg2.Label(16, 14, "Привет из PG2!", "#ffffff", 22))

    def update(self, dt):
        if self.game.clicked:
            x, y = self.game.world_mouse()
            self.burst(x, y, 30, ["#ffd166", "#ff5370", "#7fd962"], 220, .8, 4)
            self.game.beep(660, 40)


if __name__ == "__main__":
    pg2.run(Main, title="Моя игра")
'''

PG2_TEMPLATES = {"platformer": ("platformer.py", PLATFORMER), "shooter": ("shooter.py", SHOOTER), "blank": ("game.py", BLANK)}
