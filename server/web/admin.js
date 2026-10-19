"use strict";
const $ = (s) => document.querySelector(s);
const PRESETS = [
  "Произошла ошибка. Мы уже чиним — попробуй через несколько минут.",
  "Плановые работы. Скоро вернёмся.",
  "Обновление. Подожди пару минут.",
];
let token = sessionStorage.getItem("pf_token") || "";
let current = null;
let timer = null;

async function api(path, body) {
  const opts = { headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" } };
  if (body) { opts.method = "POST"; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || "Ошибка " + r.status);
  return data;
}

function show(logged) {
  $("#login").hidden = logged;
  $("#panel").hidden = !logged;
}

function fmt(t) {
  const d = new Date(t);
  return isNaN(d) ? "" : d.toLocaleString("ru-RU");
}

async function refresh() {
  try {
    current = await api("/api/status");
    const on = current.enabled;
    $("#badge").textContent = on ? "🟢 Сервер работает" : "🔴 Сервер отключён";
    $("#since").textContent = current.updated ? "с " + fmt(current.updated) : "";
    const b = $("#toggle");
    b.textContent = on ? "ОТКЛЮЧИТЬ СЕРВЕР" : "ВКЛЮЧИТЬ СЕРВЕР";
    b.className = "big " + (on ? "off" : "on");
    if (document.activeElement !== $("#msg")) $("#msg").value = on ? $("#msg").value : current.message;
    const log = await api("/api/admin/log");
    const ul = $("#log");
    ul.replaceChildren(...log.slice(0, 15).map((e) => {
      const li = document.createElement("li");
      li.textContent = fmt(e.time) + " — " + (e.enabled ? "включён" : "отключён: " + e.message);
      return li;
    }));
    $("#err").textContent = "";
  } catch (e) {
    $("#err").textContent = e.message;
    if (/токен/.test(e.message)) logout();
  }
}

async function toggle() {
  const turnOff = current && current.enabled;
  if (turnOff && !confirm("Отключить сервер? Пользователи увидят сообщение об ошибке.")) return;
  try {
    await api("/api/admin/set", { enabled: !turnOff, message: $("#msg").value });
    await refresh();
  } catch (e) { $("#err").textContent = e.message; }
}

function login() {
  token = $("#token").value.trim();
  sessionStorage.setItem("pf_token", token);
  show(true);
  refresh();
  timer = setInterval(refresh, 5000);
}

function logout() {
  sessionStorage.removeItem("pf_token");
  token = "";
  clearInterval(timer);
  show(false);
}

$("#enter").onclick = login;
$("#token").onkeydown = (e) => { if (e.key === "Enter") login(); };
$("#toggle").onclick = toggle;
$("#exit").onclick = logout;
PRESETS.forEach((p) => {
  const b = document.createElement("button");
  b.textContent = p.length > 28 ? p.slice(0, 26) + "…" : p;
  b.onclick = () => { $("#msg").value = p; };
  $("#chips").append(b);
});
$("#msg").value = PRESETS[0];
if (token) login();
