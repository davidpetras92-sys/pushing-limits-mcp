# pushinglimits-mcp

Lokaler MCP-Server (stdio) für Trainingsdaten aus [Pushing Limits Club](https://pushinglimits.club).
Liefert Plan, Ist, TSS und CTL/ATL/TSB ohne Browser, damit Claude Desktop jeden Morgen
das Trainings-Cockpit befüllen kann, so wie mit dem Garmin-MCP.

Spezifikation und Login-Analyse: [SPEC.md](SPEC.md).

Privates Hobbyprojekt ohne Verbindung zu Pushing Limits Club. Der Server liest ausschließlich
die Daten des eigenen Accounts über die interne API der Web-App, die sich jederzeit ändern kann.
Nutzung auf eigene Verantwortung.

## Wie der Login funktioniert

- Zugangsdaten liegen ausschließlich im macOS-Schlüsselbund (Service `pushinglimits-mcp`).
  Der Server liest E-Mail und Passwort zur Laufzeit mit `security find-generic-password`.
- Login: `POST /api/user/login_session` mit `{email, password}`. Die Antwort setzt ein
  HttpOnly-Session-Cookie. Alle weiteren Aufrufe laufen nur mit diesem Cookie.
- Das Cookie wird unter `~/Library/Application Support/pushinglimits-mcp/session.json`
  (Rechte 600) gespeichert. Cloudflare-Cookies (`__cf_bm`) werden nicht gespeichert.
- Ablauf pro Request: Session laden, Request, bei 401/403 genau ein Re-Login, Request
  wiederholen. Schlägt das fehl, kommt `{"error": "login_failed", "reason": ...}` zurück.
  Es gibt keinen Retry-Loop; Timeout 20 s.

## Einrichtung

1. Passwort einmalig in den Schlüsselbund legen (ohne spitze Klammern, Passwort wird abgefragt):

   ```
   security add-generic-password -s pushinglimits-mcp -a deine@mail.de -w
   ```

2. Repo klonen und Abhängigkeiten installieren:

   ```
   git clone https://github.com/davidpetras92-sys/pushing-limits-mcp.git ~/mcp/pushinglimits-mcp
   cd ~/mcp/pushinglimits-mcp && uv sync
   ```

3. In `~/Library/Application Support/Claude/claude_desktop_config.json` unter `mcpServers` eintragen.
   Claude Desktop braucht absolute Pfade, `~` also durch den eigenen Home-Ordner ersetzen
   (Pfad zu `uv` mit `which uv` prüfen):

   ```json
   "pushinglimits": {
     "command": "/Users/DEIN-NAME/.local/bin/uv",
     "args": ["--directory", "/Users/DEIN-NAME/mcp/pushinglimits-mcp", "run", "pushinglimits-mcp"]
   }
   ```

4. Claude Desktop neu starten. Beim ersten Zugriff fragt macOS einmal nach Erlaubnis für den
   Schlüsselbund. Dort „Immer erlauben" wählen, sonst hängt der Server im Hintergrund.

## Tools

Datumsparameter immer `YYYY-MM-DD`, Tagesgrenzen in Europe/Berlin.

### `pl_status()`

```json
{"logged_in": true, "user_name": "deine@mail.de", "checked_at": "2026-09-25T13:17:03+02:00"}
```

### `pl_get_pmc(start_date, end_date)`

Eine Zeile pro Tag, eine Nachkommastelle. `tss` ist die Tageslast (`load` der API).

```json
[{"date": "2026-09-24", "ctl": 100.1, "atl": 133.6, "tsb": -33.6, "tss": 98.0},
 {"date": "2026-09-25", "ctl": 98.4, "atl": 116.1, "tsb": -17.7, "tss": 0.0}]
```

### `pl_get_workouts(start_date, end_date)`

Kompakte Liste ohne `description`. Dauer in Minuten, Distanz in km (wie von der API geliefert),
`tss_is` = `pss`, `tss_plan` = `loadEstimate`, `planned` = `belongsToActivatedPlan`.

```json
[{"date": "2026-09-22", "order": 1, "name": "Aktivierungslauf", "sport": "Laufen", "planned": true,
  "duration_min_is": 37.7, "duration_min_plan": 40.0, "distance_is": 5.6, "distance_plan": 0,
  "tss_is": 28.0, "tss_plan": 29.0, "hr_avg_is": 145, "hr_avg_plan": 0, "power_avg_is": 345}]
```

### `pl_get_week(date)`

Montag bis Sonntag der Woche, mit Summen und Status je Einheit:
`erledigt` (Ist-Dauer vorhanden), `ausgelassen` (Tag vorbei, keine Ist-Dauer), sonst `offen`.
Einheiten des heutigen Tages bleiben bis Mitternacht `offen`.

```json
{"week_start": "2026-09-21", "week_end": "2026-09-27", "tss_is_sum": 418.0, "tss_plan_sum": 584.0,
 "workouts": [{"date": "2026-09-23", "order": 3, "name": "30min Mobility/Blackroll", "sport": "Kraft",
               "planned": true, "duration_min_is": 0.0, "duration_min_plan": 30.0, "tss_is": 0.0,
               "tss_plan": 23.0, "status": "ausgelassen"}]}
```

### `pl_get_thresholds()`

```json
{"ftp": 271, "threshold_run": 311, "threshold_swim": 110, "weight": 93.2,
 "max_hr": 198, "resting_hr": 55, "updated_at": "2026-09-24T18:31:40.683Z"}
```

## Fehlerbehebung

| Antwort | Bedeutung | Abhilfe |
|---|---|---|
| `login_failed` / `keychain` | Kein Eintrag `pushinglimits-mcp` im Schlüsselbund oder Zugriff verweigert | Befehl aus Schritt 1 ausführen; beim macOS-Dialog „Immer erlauben" wählen |
| `login_failed` / `bad_credentials` | Server lehnt E-Mail/Passwort ab | Eintrag löschen (`security delete-generic-password -s pushinglimits-mcp`) und neu anlegen |
| `login_failed` / `captcha_required` | Pushing Limits verlangt ein Cloudflare-Captcha (HTTP 428) | Später erneut versuchen oder einmal im Browser einloggen; tritt das dauerhaft auf, Browser-Login-Skript ergänzen |
| `login_failed` / `session_rejected` | Direkt nach erfolgreichem Login weiterhin 401/403 | Session-Datei löschen und erneut versuchen; sonst API-Änderung prüfen |
| `login_failed` / `network` | Timeout (20 s) oder keine Verbindung | Netz prüfen, erneut versuchen |
| `api_error` | Unerwarteter Status oder kein JSON | Endpoint in SPEC.md gegen die Web-App prüfen (JS-Bundle `/js/app.*.js`) |
| Abgelaufene Session | Wird automatisch erkannt (401) und einmal erneuert | Nichts zu tun; notfalls `session.json` löschen |

Session-Datei zurücksetzen:

```
rm ~/Library/Application\ Support/pushinglimits-mcp/session.json
```

## Entwicklung

```
uv sync
uv run pytest
```

Die Tests nutzen gemockte HTTP-Antworten und keine echten Zugangsdaten.

## Lizenz

MIT, siehe [LICENSE](LICENSE).
