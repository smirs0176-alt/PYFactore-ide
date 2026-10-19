"""Своя нейросеть PyFactor: маленькая сеть, которая учится на твоём коде и предсказывает следующее слово.
Чистый Python, без библиотек. Вход: 3 последних токена -> эмбеддинги -> скрытый слой (tanh) -> softmax."""
import json
import math
import random
import re
import time
from collections import Counter
from operator import mul

TOK = re.compile(r"[A-Za-z_]\w*|\d+|\n|[^\sA-Za-z_\d]")
WORD = re.compile(r"[A-Za-z_]\w*$")
CTX, D, H, VMAX = 3, 10, 20, 260


def tokens(code):
    return TOK.findall(code)


class Brain:
    def __init__(self):
        self.vocab, self.idx, self.ready = ["<unk>"], {}, False
        self.E = self.W1 = self.b1 = self.W2 = self.b2 = None
        self.info = ""

    def _ids(self, ts):
        pad = self.idx.get("\n", 0)
        return [self.idx.get(t, 0) for t in ts], pad

    def _fwd(self, ctx):
        x = []
        for c in ctx:
            x += self.E[c]
        h = [math.tanh(sum(map(mul, w, x)) + b) for w, b in zip(self.W1, self.b1)]
        z = [sum(map(mul, w, h)) + b for w, b in zip(self.W2, self.b2)]
        m = max(z)
        e = [math.exp(v - m) for v in z]
        s = sum(e)
        return x, h, [v / s for v in e]

    def _init(self, V):
        r = random.Random(1)
        self.E = [[r.uniform(-.3, .3) for _ in range(D)] for _ in range(V)]
        self.W1 = [[r.uniform(-.25, .25) for _ in range(CTX * D)] for _ in range(H)]
        self.b1 = [0.0] * H
        self.W2 = [[r.uniform(-.25, .25) for _ in range(H)] for _ in range(V)]
        self.b2 = [0.0] * V

    def train(self, texts, seconds=30, lr=0.08):
        seqs = [tokens(t) for t in texts]
        cnt = Counter(w for s in seqs for w in s)
        self.vocab = ["<unk>"] + [w for w, _ in cnt.most_common(VMAX - 1)]
        self.idx = {w: i for i, w in enumerate(self.vocab)}
        V = len(self.vocab)
        self._init(V)
        data = []
        for s in seqs:
            ids, pad = self._ids(s)
            for i, t in enumerate(ids):
                if t:
                    c = ([pad] * CTX + ids[:i])[-CTX:]
                    data.append((c, t))
        if len(data) < 50:
            return 0
        random.shuffle(data)
        data = data[:40000]
        end, n, ep = time.time() + seconds, 0, 0
        while time.time() < end and ep < 40:
            ep += 1
            random.shuffle(data)
            for c, t in data:
                if n % 300 == 0 and time.time() > end:
                    break
                n += 1
                self._step(c, t, lr)
        hit = sum(1 for c, t in data[:2000] if t in sorted(range(V), key=self._fwd(c)[2].__getitem__)[-5:])
        self.ready = True
        self.info = "слов %d, примеров %d, эпох %d, точность top-5: %d%%" % (V, len(data), ep, 100 * hit // min(2000, len(data)))
        return n

    def _step(self, c, t, lr):
        x, h, p = self._fwd(c)
        dh = [0.0] * H
        for v in range(len(p)):
            g = p[v] - (1 if v == t else 0)
            if abs(g) < 0.004:
                continue
            w = self.W2[v]
            for j in range(H):
                dh[j] += g * w[j]
                w[j] -= lr * g * h[j]
            self.b2[v] -= lr * g
        dx = [0.0] * (CTX * D)
        for j in range(H):
            d = dh[j] * (1 - h[j] * h[j])
            w = self.W1[j]
            for k in range(CTX * D):
                dx[k] += d * w[k]
                w[k] -= lr * d * x[k]
            self.b1[j] -= lr * d
        for i, ci in enumerate(c):
            e = self.E[ci]
            for k in range(D):
                e[k] -= lr * dx[i * D + k]

    def predict(self, before, prefix="", k=6):
        """before — текст перед курсором без набираемого слова. Возвращает [(слово, вероятность)]."""
        if not self.ready:
            return []
        ids, pad = self._ids(tokens(before)[-CTX:])
        p = self._fwd(([pad] * CTX + ids)[-CTX:])[2]
        out = []
        for v in sorted(range(len(p)), key=p.__getitem__, reverse=True):
            w = self.vocab[v]
            if WORD.match(w) and w != "<unk>" and w != prefix and w.lower().startswith(prefix.lower()):
                out.append((w, p[v]))
                if len(out) >= k:
                    break
        return out

    def save(self, path):
        r = lambda m: [[round(a, 4) for a in row] for row in m]
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"v": self.vocab, "E": r(self.E), "W1": r(self.W1), "b1": self.b1,
                       "W2": r(self.W2), "b2": self.b2, "info": self.info}, f)

    def load(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            self.vocab, self.E, self.W1, self.b1, self.W2, self.b2 = d["v"], d["E"], d["W1"], d["b1"], d["W2"], d["b2"]
            self.idx = {w: i for i, w in enumerate(self.vocab)}
            self.info, self.ready = d.get("info", ""), True
        except Exception:
            self.ready = False
        return self.ready
