# PocketSmart-AI
# PocketSmart AI

PocketSmart AI is a budget planning web app for home interiors, parties, and jewelry. Enter a budget and your preferences to get an organized starter plan with estimated costs, practical suggestions, and links for comparing options.

The app uses FastAPI, Jinja templates, vanilla JavaScript, and SQLite. Gemini recommendations are optional: local planning logic keeps all three planners available when no Gemini API key is configured or a Gemini request fails.

## Features

- **Home planner:** Organize a budget by room and requested items, including quantities and optional style or location details.
- **Party planner:** Plan around an event type, guest count, budget, and optional preferences such as venue or dietary needs.
- **Jewelry planner:** Explore ideas by budget, occasion, and style. An outfit description or image can be added for optional context.
- **Structured plans:** Review a summary, estimated budget allocations, item or service ideas, and savings or style notes.
- **Saved history:** Create an account to save plans and revisit them later.
- **Local fallback:** Continue planning without Gemini or when an AI request is unavailable.

All amounts are planning estimates. Retailer buttons open search pages for Amazon India, Flipkart, IKEA, Swiggy, Zomato, or OYO. The app does not scrape retailer websites or verify live listings, current prices, stock, delivery, or service terms.

## Requirements

- Python 3.11 or newer
- Visual Studio Code with the Python extension, or another Python environment
- A Gemini API key only if you want Gemini-backed recommendations

## Install

Open a terminal in the project folder and run:

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
~~~

If this is a fresh project copy and .env does not exist, create it from the example:

~~~powershell
Copy-Item .env.example .env
~~~

Keep .env private and out of source control. Add your key to GEMINI_API_KEY only if you want to use Gemini. The local fallback does not require a key.

For production, replace the development APP_SECRET_KEY with a long random value. Set APP_ENV=production and COOKIE_SECURE=true when the app is served over HTTPS.

## Run

With the virtual environment active, start the app from the project root:

~~~powershell
python -m uvicorn app.main:app --reload
~~~

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The interactive API reference is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). SQLite creates data/pocketsmart.sqlite3 when the app starts.

## Try the planners

1. Register an account or sign in.
2. Choose Home, Party, or Jewelry from the dashboard.
3. Enter a budget and the required planner details, then submit the form.
4. Review the plan and follow search links to compare options with providers.
5. Open **History** to revisit a saved plan, then sign out when finished.

The Jewelry planner accepts JPG, PNG, and WebP images, up to 5 MB by default. An uploaded image is used only for the jewelry request, is not saved to plan history, and is sent to Gemini only when Gemini is configured.

## Main routes

| Purpose | Route |
|---|---|
| Landing page | GET / |
| Register or sign in pages | GET /register, GET /login |
| Dashboard and planner pages | GET /dashboard, GET /planner/{planner_type} |
| Account actions | POST /register, POST /login, POST /logout |
| Generate plans | POST /generate-home, POST /generate-party, POST /generate-jewelry |
| Plan history | GET /history, GET /api/history |
| Saved plan details | GET /recommendations-details/{id} |
| Readiness and session | GET /health, GET /startup, GET /session-info |
| Bearer token | POST /token |

Cookie-authenticated write requests require the CSRF header used by the included frontend. API clients can use the bearer token returned by /token.

## Project structure

~~~text
PocketSmartAI/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── schemas.py
│   ├── security.py
│   ├── services/recommendations.py
│   ├── static/
│   └── templates/
├── data/
├── tests/
├── .env.example
└── requirements.txt
~~~

app/main.py defines pages and API routes. app/schemas.py validates requests, app/security.py handles password hashing and signed tokens, app/database.py manages SQLite data, and app/services/recommendations.py builds plans with Gemini or local fallback logic.

## Run the automated checks

After installing the requirements, run:

~~~powershell
python -m unittest discover -s tests -v
~~~

The test suite uses temporary SQLite storage and disables Gemini. The README describes coverage for authentication, CSRF protection, all three planners, budget limits, search links, saved history, bearer-token authentication, and invalid image uploads.

## Privacy and planning boundaries

Passwords are stored as salted PBKDF2-SHA256 hashes. Signed sessions use expiring tokens; cookie-authenticated write requests also check a CSRF token. Keep environment secrets and the SQLite database private.

PocketSmart AI helps users prepare and compare a budget plan. It does not provide verified product listings, live prices, guaranteed availability, or purchase checkout. Confirm details and terms on the provider's website before making a purchase.
