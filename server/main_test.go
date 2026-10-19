package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const tok = "0123456789abcdef-test-token"

func setup(t *testing.T) (*Server, http.Handler, string) {
	t.Helper()
	f := filepath.Join(t.TempDir(), "state.json")
	s := newServer(tok, f)
	return s, s.handler(), f
}

func do(h http.Handler, method, path, auth, body, remote string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, path, strings.NewReader(body))
	if auth != "" {
		r.Header.Set("Authorization", auth)
	}
	if remote != "" {
		r.RemoteAddr = remote
	}
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	return w
}

func TestStatusPublicAndMethod(t *testing.T) {
	_, h, _ := setup(t)
	if w := do(h, "GET", "/api/status", "", "", ""); w.Code != 200 || !strings.Contains(w.Body.String(), `"enabled":true`) {
		t.Fatalf("status: %d %s", w.Code, w.Body)
	}
	if w := do(h, "POST", "/api/status", "", "", ""); w.Code != 405 {
		t.Fatalf("POST status want 405 got %d", w.Code)
	}
}

func TestAdminRequiresStrictBearer(t *testing.T) {
	_, h, _ := setup(t)
	body := `{"enabled":false,"message":"x"}`
	for name, auth := range map[string]string{"none": "", "wrong": "Bearer nope", "raw token without Bearer": tok, "empty bearer": "Bearer "} {
		if w := do(h, "POST", "/api/admin/set", auth, body, ""); w.Code != 401 {
			t.Errorf("%s: want 401 got %d", name, w.Code)
		}
	}
	if w := do(h, "GET", "/api/admin/log", "", "", ""); w.Code != 401 {
		t.Errorf("log without token: %d", w.Code)
	}
	if w := do(h, "GET", "/api/admin/set", "Bearer "+tok, "", ""); w.Code != 405 {
		t.Errorf("GET set want 405 got %d", w.Code)
	}
}

func TestSetPersistsAndSanitizes(t *testing.T) {
	s, h, f := setup(t)
	msg := "Чиним\x00\x07 сервер\nскоро " + strings.Repeat("я", 600)
	b, _ := json.Marshal(map[string]any{"enabled": false, "message": msg})
	w := do(h, "POST", "/api/admin/set", "Bearer "+tok, string(b), "")
	if w.Code != 200 {
		t.Fatalf("set: %d %s", w.Code, w.Body)
	}
	if strings.ContainsAny(s.state.Message, "\x00\x07\n") || len([]rune(s.state.Message)) != 500 {
		t.Fatalf("message not sanitized: %d runes", len([]rune(s.state.Message)))
	}
	s2 := newServer(tok, f)
	s2.load()
	if s2.state.Enabled || s2.state.Message != s.state.Message {
		t.Fatal("state not restored after restart")
	}
	if st, _ := os.Stat(f); st.Mode().Perm() != 0o600 {
		t.Errorf("state file mode %v", st.Mode().Perm())
	}
	if m, _ := filepath.Glob(f + ".*.tmp"); len(m) != 0 {
		t.Errorf("temp files left: %v", m)
	}
}

func TestDisabledWithoutMessageGetsDefaultAndEnableClears(t *testing.T) {
	s, h, _ := setup(t)
	do(h, "POST", "/api/admin/set", "Bearer "+tok, `{"enabled":false}`, "")
	if s.state.Message != defaultMsg {
		t.Fatalf("default message missing: %q", s.state.Message)
	}
	do(h, "POST", "/api/admin/set", "Bearer "+tok, `{"enabled":true,"message":"ignored"}`, "")
	if !s.state.Enabled || s.state.Message != "" {
		t.Fatalf("enable should clear message: %+v", s.state)
	}
}

func TestBadBodiesRejected(t *testing.T) {
	_, h, _ := setup(t)
	for name, body := range map[string]string{"no enabled": `{"message":"x"}`, "not json": `nope`, "huge": `{"enabled":true,"message":"` + strings.Repeat("a", 10000) + `"}`} {
		if w := do(h, "POST", "/api/admin/set", "Bearer "+tok, body, ""); w.Code != 400 {
			t.Errorf("%s: want 400 got %d", name, w.Code)
		}
	}
}

func TestBruteForceLockoutPerIP(t *testing.T) {
	_, h, _ := setup(t)
	for i := 0; i < authFails; i++ {
		if w := do(h, "GET", "/api/admin/log", "Bearer bad", "", "1.2.3.4:5555"); w.Code != 401 {
			t.Fatalf("attempt %d: %d", i, w.Code)
		}
	}
	if w := do(h, "GET", "/api/admin/log", "Bearer "+tok, "", "1.2.3.4:5555"); w.Code != 429 {
		t.Fatalf("correct token from locked IP must be 429, got %d", w.Code)
	}
	if w := do(h, "GET", "/api/admin/log", "Bearer "+tok, "", "5.6.7.8:1"); w.Code != 200 {
		t.Fatalf("other IP must be unaffected, got %d", w.Code)
	}
}

func TestForwardedForUsesLastEntryOnlyWhenTrusted(t *testing.T) {
	s, _, _ := setup(t)
	r := httptest.NewRequest("GET", "/", nil)
	r.RemoteAddr = "10.0.0.1:1"
	r.Header.Set("X-Forwarded-For", "6.6.6.6, 9.9.9.9")
	if got := s.clientIP(r); got != "10.0.0.1" {
		t.Errorf("untrusted proxy: got %s", got)
	}
	s.trustProxy = true
	if got := s.clientIP(r); got != "9.9.9.9" {
		t.Errorf("trusted proxy must use last entry, got %s", got)
	}
	r.Header.Set("X-Forwarded-For", "garbage")
	if got := s.clientIP(r); got != "10.0.0.1" {
		t.Errorf("invalid XFF must fall back, got %s", got)
	}
}

func TestCorruptStateFallsBackToEnabled(t *testing.T) {
	_, _, f := setup(t)
	_ = os.WriteFile(f, []byte("{broken"), 0o600)
	s := newServer(tok, f)
	s.load()
	if !s.state.Enabled {
		t.Fatal("corrupt state must not disable the server")
	}
}

func TestResolveTokenNeverLogsAndValidatesLength(t *testing.T) {
	dir := t.TempDir()
	sf := filepath.Join(dir, "state.json")
	t.Setenv("ADMIN_TOKEN", "short")
	if _, err := resolveToken(sf); err == nil {
		t.Fatal("short token must be refused")
	}
	t.Setenv("ADMIN_TOKEN", "")
	got, err := resolveToken(sf)
	if err != nil || len(got) < minTokenLen {
		t.Fatalf("generated token: %q %v", got, err)
	}
	b, _ := os.ReadFile(filepath.Join(dir, "admin_token.txt"))
	if strings.TrimSpace(string(b)) != got {
		t.Fatal("token file mismatch")
	}
	if st, _ := os.Stat(filepath.Join(dir, "admin_token.txt")); st.Mode().Perm() != 0o600 {
		t.Errorf("token file mode %v", st.Mode().Perm())
	}
}

func TestSecurityHeadersAndAdminPage(t *testing.T) {
	s, _, _ := setup(t)
	s.secure = true
	h := s.handler()
	w := do(h, "GET", "/admin/", "", "", "")
	if w.Code != 200 {
		t.Fatalf("admin page %d", w.Code)
	}
	for _, k := range []string{"Content-Security-Policy", "X-Content-Type-Options", "Strict-Transport-Security", "X-Frame-Options"} {
		if w.Header().Get(k) == "" {
			t.Errorf("missing header %s", k)
		}
	}
	if w := do(h, "GET", "/nope", "", "", ""); w.Code != 404 {
		t.Errorf("unknown path %d", w.Code)
	}
}
