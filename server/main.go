// Сервер-выключатель PyFactor. Один файл, только стандартная библиотека Go.
//
//	ADMIN_TOKEN=секрет-не-короче-16-символов PORT=8080 go run .
//
// Публично:  GET /api/status          -> {"enabled":true,"message":"","updated":"..."}
// По токену: POST /api/admin/set      {"enabled":false,"message":"..."}
//
//	GET  /api/admin/log
//
// Панель управления: /admin/
//
// Переменные окружения:
//
//	ADMIN_TOKEN   токен администратора (не короче 16 символов). Не задан — создаётся случайный и
//	              записывается в файл admin_token.txt (права 0600), в лог он НЕ попадает.
//	PORT          порт (по умолчанию 8080)
//	STATE_FILE    файл состояния (по умолчанию state.json)
//	SECURE=1      сервер стоит за HTTPS: добавляется заголовок HSTS
//	TRUST_PROXY=1 сервер стоит за nginx/Caddy: адрес клиента берётся из последнего значения X-Forwarded-For
package main

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io/fs"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
	"unicode/utf8"
)

//go:embed web
var webFS embed.FS

const (
	defaultMsg   = "Произошла ошибка. Мы уже чиним — попробуй через несколько минут."
	minTokenLen  = 16
	maxMsgRunes  = 500
	maxBodyBytes = 4096
	authFails    = 10              // неверных попыток с одного адреса ...
	authWindow   = 5 * time.Minute // ... за это время, после чего ответ 429
)

type State struct {
	Enabled bool   `json:"enabled"`
	Message string `json:"message"`
	Updated string `json:"updated"`
}

type Entry struct {
	Time    string `json:"time"`
	Enabled bool   `json:"enabled"`
	Message string `json:"message"`
	IP      string `json:"ip"`
}

// limiter — ограничитель неверных попыток по адресу (в памяти).
type limiter struct {
	mu   sync.Mutex
	hits map[string][]time.Time
}

func newLimiter() *limiter { return &limiter{hits: map[string][]time.Time{}} }

func (l *limiter) prune(key string, now time.Time) []time.Time {
	var keep []time.Time
	for _, t := range l.hits[key] {
		if now.Sub(t) < authWindow {
			keep = append(keep, t)
		}
	}
	if len(keep) == 0 {
		delete(l.hits, key)
	} else {
		l.hits[key] = keep
	}
	return keep
}

func (l *limiter) blocked(key string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	return len(l.prune(key, time.Now())) >= authFails
}

func (l *limiter) fail(key string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	now := time.Now()
	if len(l.hits) > 10000 { // защита памяти от перебора адресов
		for k := range l.hits {
			l.prune(k, now)
		}
	}
	l.hits[key] = append(l.prune(key, now), now)
}

func (l *limiter) reset(key string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	delete(l.hits, key)
}

type Server struct {
	mu         sync.RWMutex
	state      State
	history    []Entry
	token      string
	stateFile  string
	secure     bool
	trustProxy bool
	lim        *limiter
}

func envOr(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

// writeFileAtomic пишет во временный файл рядом и переименовывает: обрыв записи не портит старый файл.
func writeFileAtomic(path string, data []byte, perm os.FileMode) error {
	tmp, err := os.CreateTemp(filepath.Dir(path), filepath.Base(path)+".*.tmp")
	if err != nil {
		return err
	}
	name := tmp.Name()
	cleanup := func() { _ = os.Remove(name) }
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		cleanup()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		cleanup()
		return err
	}
	if err := tmp.Close(); err != nil {
		cleanup()
		return err
	}
	if err := os.Chmod(name, perm); err != nil {
		cleanup()
		return err
	}
	if err := os.Rename(name, path); err != nil {
		cleanup()
		return err
	}
	return nil
}

// cleanMessage обрезает сообщение по символам (не ломая UTF-8) и убирает управляющие символы.
func cleanMessage(s string) string {
	s = strings.Map(func(r rune) rune {
		if r == '\n' || r == '\t' {
			return ' '
		}
		if r < 32 || r == 127 || r == utf8.RuneError {
			return -1
		}
		return r
	}, s)
	s = strings.TrimSpace(s)
	if r := []rune(s); len(r) > maxMsgRunes {
		s = string(r[:maxMsgRunes])
	}
	return s
}

func (s *Server) load() {
	b, err := os.ReadFile(s.stateFile)
	if errors.Is(err, os.ErrNotExist) {
		return
	}
	if err != nil {
		log.Println("не удалось прочитать состояние:", err)
		return
	}
	var st State
	if err := json.Unmarshal(b, &st); err != nil {
		log.Println("файл состояния повреждён, начинаю с включённого сервера:", err)
		return
	}
	st.Message = cleanMessage(st.Message)
	s.state = st
}

// save вызывается под s.mu.
func (s *Server) save() {
	b, _ := json.MarshalIndent(s.state, "", "  ")
	if err := writeFileAtomic(s.stateFile, b, 0o600); err != nil {
		log.Println("не удалось сохранить состояние:", err)
	}
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

// clientIP: за прокси берём ПОСЛЕДНЕЕ значение X-Forwarded-For — его дописал наш прокси, остальное подделывает клиент.
func (s *Server) clientIP(r *http.Request) string {
	if s.trustProxy {
		if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
			parts := strings.Split(xff, ",")
			if ip := strings.TrimSpace(parts[len(parts)-1]); net.ParseIP(ip) != nil {
				return ip
			}
		}
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

// bearer возвращает токен только из строгого вида "Bearer <токен>".
func bearer(r *http.Request) string {
	const p = "Bearer "
	h := r.Header.Get("Authorization")
	if len(h) > len(p) && strings.EqualFold(h[:len(p)], p) {
		return strings.TrimSpace(h[len(p):])
	}
	return ""
}

func (s *Server) authed(w http.ResponseWriter, r *http.Request) bool {
	ip := s.clientIP(r)
	if s.lim.blocked(ip) {
		w.Header().Set("Retry-After", "300")
		writeJSON(w, http.StatusTooManyRequests, map[string]string{"error": "слишком много неверных попыток, подожди несколько минут"})
		return false
	}
	got := bearer(r)
	if subtle.ConstantTimeCompare([]byte(got), []byte(s.token)) != 1 {
		s.lim.fail(ip)
		writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "неверный токен"})
		return false
	}
	s.lim.reset(ip)
	return true
}

func methodOnly(m string, h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != m {
			w.Header().Set("Allow", m)
			writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "нужен " + m})
			return
		}
		h(w, r)
	}
}

func (s *Server) status(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	writeJSON(w, 200, s.state)
}

func (s *Server) set(w http.ResponseWriter, r *http.Request) {
	if !s.authed(w, r) {
		return
	}
	var in struct {
		Enabled *bool  `json:"enabled"`
		Message string `json:"message"`
	}
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxBodyBytes))
	if err := dec.Decode(&in); err != nil || in.Enabled == nil {
		writeJSON(w, 400, map[string]string{"error": "ожидается {\"enabled\":true|false,\"message\":\"...\"}"})
		return
	}
	msg := cleanMessage(in.Message)
	if !*in.Enabled && msg == "" {
		msg = defaultMsg
	}
	if *in.Enabled {
		msg = ""
	}
	ip := s.clientIP(r)
	s.mu.Lock()
	s.state = State{Enabled: *in.Enabled, Message: msg, Updated: time.Now().Format(time.RFC3339)}
	s.history = append([]Entry{{s.state.Updated, s.state.Enabled, msg, ip}}, s.history...)
	if len(s.history) > 50 {
		s.history = s.history[:50]
	}
	s.save()
	cur := s.state
	s.mu.Unlock()
	log.Printf("enabled=%v message=%q от %s", cur.Enabled, cur.Message, ip)
	writeJSON(w, 200, cur)
}

func (s *Server) journal(w http.ResponseWriter, r *http.Request) {
	if !s.authed(w, r) {
		return
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	h := s.history
	if h == nil {
		h = []Entry{}
	}
	writeJSON(w, 200, h)
}

// secure добавляет защитные заголовки ко всем ответам.
func (s *Server) secureHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := w.Header()
		h.Set("X-Content-Type-Options", "nosniff")
		h.Set("Referrer-Policy", "no-referrer")
		h.Set("X-Frame-Options", "DENY")
		if s.secure {
			h.Set("Strict-Transport-Security", "max-age=31536000")
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) handler() http.Handler {
	web, err := fs.Sub(webFS, "web")
	if err != nil {
		log.Fatal(err)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/api/status", methodOnly(http.MethodGet, s.status))
	mux.HandleFunc("/api/admin/set", methodOnly(http.MethodPost, s.set))
	mux.HandleFunc("/api/admin/log", methodOnly(http.MethodGet, s.journal))
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) { _, _ = w.Write([]byte("ok")) })
	files := http.StripPrefix("/admin/", http.FileServer(http.FS(web)))
	mux.HandleFunc("/admin/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Security-Policy",
			"default-src 'self'; style-src 'self' 'unsafe-inline'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
		w.Header().Set("Cache-Control", "no-store")
		files.ServeHTTP(w, r)
	})
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" && r.URL.Path != "/admin" {
			http.NotFound(w, r)
			return
		}
		http.Redirect(w, r, "/admin/", http.StatusFound)
	})
	return s.secureHeaders(mux)
}

func newServer(token, stateFile string) *Server {
	return &Server{state: State{Enabled: true}, token: token, stateFile: stateFile, lim: newLimiter()}
}

// resolveToken берёт токен из ADMIN_TOKEN или создаёт случайный и кладёт в файл рядом с состоянием.
func resolveToken(stateFile string) (string, error) {
	if t := os.Getenv("ADMIN_TOKEN"); t != "" {
		if len(t) < minTokenLen {
			return "", errors.New("ADMIN_TOKEN слишком короткий: нужно минимум 16 символов")
		}
		return t, nil
	}
	b := make([]byte, 24)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	t := hex.EncodeToString(b)
	path := filepath.Join(filepath.Dir(stateFile), "admin_token.txt")
	if err := writeFileAtomic(path, []byte(t+"\n"), 0o600); err != nil {
		return "", err
	}
	log.Printf("ADMIN_TOKEN не задан: создан временный токен, он записан в файл %s (в лог не выводится)", path)
	return t, nil
}

func main() {
	stateFile := envOr("STATE_FILE", "state.json")
	token, err := resolveToken(stateFile)
	if err != nil {
		log.Fatal(err)
	}
	s := newServer(token, stateFile)
	s.secure = os.Getenv("SECURE") == "1"
	s.trustProxy = os.Getenv("TRUST_PROXY") == "1"
	s.load()
	addr := ":" + envOr("PORT", "8080")
	srv := &http.Server{
		Addr: addr, Handler: s.handler(), MaxHeaderBytes: 16 << 10,
		ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second,
		WriteTimeout: 10 * time.Second, IdleTimeout: 60 * time.Second,
	}
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	go func() {
		<-stop
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(ctx)
	}()
	log.Printf("PyFactor-сервер на %s, панель: /admin/", addr)
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}
