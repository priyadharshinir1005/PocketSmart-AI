# PocketSmart AI

PocketSmart AI is a responsive budget planning app for home interiors, parties, and jewelry. It uses FastAPI, Jinja templates, vanilla JavaScript, and SQLite. When a Gemini API key is configured, the recommendation service calls Gemini for a structured plan and can include an optional outfit image for jewelry. Without a key, built-in local planning logic keeps all three planners usable.

Recommendation amounts are planning estimates. Retailer buttons open search pages for Amazon India, Flipkart, IKEA, Swiggy, Zomato, or OYO; they do not represent live catalog results, verified listings, current prices, or availability. The app does not scrape retailer websites. An uploaded outfit image is sent only with the jewelry request and is not written to disk or saved in recommendation history.

## Requirements

- Windows, macOS, or Linux
- Python 3.11 or newer
- Visual Studio Code with the Python extension
- A Gemini API key is optional. The local fallback works without one.

## Open in VS Code

1. Extract or copy the `PocketSmartAI` folder to a location you can edit.
2. In VS Code, choose **File → Open Folder** and select `PocketSmartAI`.
3. Open **Terminal → New Terminal**. The commands below use PowerShell on Windows.
4. Install the recommended Python extension. The included Run and Debug profile starts Uvicorn after installation.

## Install

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then activate the environment again. In VS Code, use **Python: Select Interpreter** and choose `.venv`.

### Optional Gemini setup

Open `.env` and set `GEMINI_API_KEY` to your key. The default model is `gemini-3.8-flash`; change `GEMINI_MODEL` if your account or region uses another currently available Gemini model. Keep `.env` private and out of source control. The local fallback remains available if the key is empty or a Gemini request fails.

For a deployment, replace `APP_SECRET_KEY` with a long random value and set `APP_ENV=production` and `COOKIE_SECURE=true` when serving over HTTPS. A random key can be created with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Run

From the project folder, with `.venv` active:

```powershell
python -m uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). FastAPI’s interactive API reference is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). SQLite creates `data/pocketsmart.sqlite3` on first start.

## Try the application

1. Create an account. Registration signs you in automatically.
2. Open each planner from the dashboard.
3. Submit a Home plan with one or more rooms and items; enter quantities as `Ceiling fan x 2`.
4. Submit a Party plan with an event type and guest count.
5. Submit a Jewelry plan. Add a JPG, PNG, or WebP outfit image to try the optional image input.
6. Open **History** to revisit saved plans, then sign out.
7. Visit `/health` to see whether Gemini is configured. The response does not reveal the API key.

## Run the automated checks

Install the requirements first, then run:

```powershell
python -m unittest discover -s tests -v
```

The tests use an isolated temporary SQLite database and disable Gemini so they do not need credentials or make paid API calls. They cover authentication, CSRF protection for cookie sessions, all three planners, budget limits, retailer search links, saved history, bearer-token authentication, and invalid image uploads.

## Routes

| Purpose | Route |
|---|---|
| Landing page | `GET /` |
| Account pages | `GET /login`, `GET /register` |
| Dashboard and planner pages | `GET /dashboard`, `GET /planner/home`, `/planner/party`, `/planner/jewelry` |
| Register / sign in / sign out | `POST /register`, `POST /login`, `POST /logout` |
| OAuth-compatible access token | `POST /token` |
| Home / party / jewelry recommendations | `POST /generate-home`, `/generate-party`, `/generate-jewelry` |
| Current session and personalization data | `GET /session-info`, `GET /session-data` |
| History page and history API | `GET /history`, `GET /api/history` |
| Saved plan details | `GET /recommendations-details/{id}` |
| Readiness | `GET /health`, `GET /startup` |

Cookie-authenticated write requests require the CSRF header used by the included frontend. API clients can use the bearer token returned by `/token` instead.

## Project structure

```text
PocketSmartAI/
├── app/
│   ├── main.py                 FastAPI pages, authentication, and API routes
│   ├── config.py               Environment settings
│   ├── database.py             SQLite persistence
│   ├── schemas.py              Validated request and recommendation models
│   ├── security.py             Password hashing and signed tokens
│   ├── services/
│   │   └── recommendations.py  Gemini integration and local fallback
│   ├── static/
│   │   ├── app.css
│   │   └── app.js
│   └── templates/              Jinja pages
├── data/                       Created SQLite data directory
├── .vscode/                    VS Code interpreter and debug settings
├── tests/
├── .env.example
└── requirements.txt
```
