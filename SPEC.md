# Spezifikation

## Ziel
Lokaler MCP-Server (stdio) `pushinglimits`, der Daten aus der JSON-API von Pushing Limits Club liefert, damit eine tägliche Claude-Aufgabe (Trainings-Cockpit für den Ironman Nizza am 12.09.2027) ohne Browser und ohne Freigabedialoge an Plan, TSS und CTL/ATL/TSB kommt.

## Bekannte Endpoints (Basis https://pushinglimits.club, am 25.09.2026 geprüft, alle GET, Sitzung per Cookie)
| Zweck | Endpoint | Antwort |
|---|---|---|
| Login-Check / Profil | `/api/user/me` | 200 = eingeloggt |
| Performance Management | `/api/workout/analysis/pmc?from=<unix Sek.>&until=<unix Sek.>` | `{series:[{day, ctl, atl, tsb, load}]}`, `load` = TSS des Tages |
| Einheiten Plan und Ist | `/api/workout/from/<ms>/until/<ms>` | Liste mit `name, sport, localDate, orderOfDay, durationIs, durationShould` (Sek.), `distance, distanceShould, pss` (Ist-TSS), `loadEstimate` (Plan-TSS), `heartRateAvg, heartRateAvgShould, powerInWatts, belongsToActivatedPlan, is_alternative, description` |
| Nächste Einheiten | `/api/workout/nextworkouts/<ms>/limit/<n>` | Liste |
| Schwellen | `/api/user/threshold` | `ftp, threshold_run, threshold_swim, weight, maxHr, restingHr, createdAt` |

Zeitgrenzen: Tagesbeginn 00:00 Europe/Berlin. Beispiel Woche 21.09. bis 27.09.2026: `from = 2026-09-20T22:00:00Z`, `until = 2026-09-27T21:59:59Z`.

## Sicherheit
Passwort nur im macOS-Schlüsselbund (Service `pushinglimits-mcp`). Session unter `~/Library/Application Support/pushinglimits-mcp/session.json`, Rechte 600. Nichts davon im Repo.

## Tools
`pl_status`, `pl_get_pmc`, `pl_get_workouts`, `pl_get_week`, `pl_get_thresholds` (Details siehe Schritt 5).

## Login (Ergebnis der Analyse der Web-App am 25.09.2026)
- Web-Login: `POST /api/user/login_session` mit JSON `{email, password}`. Antwort setzt ein HttpOnly-Session-Cookie; alle weiteren Aufrufe laufen nur mit diesem Cookie.
- Alternative der nativen Apps: `POST /api/user/login` liefert `{token, user}`, Token geht als `Authorization`-Header (ohne `Bearer`) mit, Auffrischung über Antwort-Header `x-jwt-refresh`.
- Captcha (Cloudflare Turnstile) nur bei Bedarf: Server antwortet mit HTTP 428 und `{code: "CAPTCHA_REQUIRED", siteKey}`. Kein 2FA gefunden.
- Ohne gültige Sitzung antwortet `/api/user/me` mit 401.
