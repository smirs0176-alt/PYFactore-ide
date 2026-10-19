#!/usr/bin/env node
// Быстрый выключатель из терминала (нужен Node 18+).
//   node switch.js status
//   node switch.js off "Произошла ошибка, чиним"
//   node switch.js on
// Переменные: PYFACTOR_SERVER (например http://localhost:8080) и PYFACTOR_ADMIN_TOKEN.
const base = (process.env.PYFACTOR_SERVER || "http://localhost:8080").replace(/\/$/, "");
const token = process.env.PYFACTOR_ADMIN_TOKEN || "";
const [cmd, ...rest] = process.argv.slice(2);

async function call(path, body) {
  const r = await fetch(base + path, {
    method: body ? "POST" : "GET",
    headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || "HTTP " + r.status);
  return data;
}

(async () => {
  try {
    if (cmd === "on" || cmd === "off") {
      const s = await call("/api/admin/set", { enabled: cmd === "on", message: rest.join(" ") });
      console.log(s.enabled ? "🟢 включён" : "🔴 отключён: " + s.message);
    } else if (cmd === "status") {
      const s = await call("/api/status");
      console.log(s.enabled ? "🟢 работает" : "🔴 отключён: " + s.message);
    } else {
      console.log("Использование: node switch.js on | off [сообщение] | status");
    }
  } catch (e) {
    console.error("Ошибка:", e.message);
    process.exit(1);
  }
})();
