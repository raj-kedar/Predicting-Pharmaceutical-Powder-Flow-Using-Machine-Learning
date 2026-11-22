# Predicting Pharmaceutical Powder Flow Using Machine Learning

Backend API that classifies pharmaceutical powder flow. It uses the exact USP <1174>
calculation when bulk and tapped density are measured, and a validated screening model
only when tapped density is missing. Every response states which method answered.

> FlowLytix is a decision-support and screening tool, **not a GMP-validated system**. Not for release testing, QC decisions or
> regulatory submission.

## Methods and performance

| Path / tier | Inputs required | Leave-one-material-out accuracy | Balanced |
|---|---|---|---|
| `rule` | bulk + tapped density | exact by definition | n/a |
| `ml` / `full` | bulk, angle of repose, particle size, moisture, flow rate | 0.920 | 0.923 |
| `ml` / `mid` | bulk, angle of repose, particle size, moisture | 0.847 | 0.844 |
| `ml` / `basic` | bulk, angle of repose | 0.828 | 0.822 |

The majority-class baseline is 0.565. Validation covers 600 rows from 70 materials in the
compiled dataset, and each test material is unseen.

The ~92% figure depends on flow rate being measured. Flow rate is not leakage, because it
comes from a separate orifice test, but it is itself a flow measurement. Quote the figure
for the inputs you actually had. Carr's index and Hausner ratio are never model inputs,
because the target is a band of Carr's index.

## Project structure

```text
api/            FastAPI service
  routers/      auth, users, classify, samples, predictions, audit, system
  db/           schema, engine, integrity triggers
  classification.py, deps.py, schemas.py, security.py, main.py
src/            ML and domain code, independent of the web layer
  data/         dataset loading
  features/     Carr's index, Hausner ratio, USP bands
  preprocessing/ physical validation
  models/       forest, engine, training, verified model loading
  evaluation/   leave-one-material-out validation
config/         development, testing and production settings
scripts/        seed, train, build_manifest, migrate_legacy_db
tests/          automated test suite
data/raw/       immutable source data (not committed)
data/app/       runtime SQLite database (not committed)
models/         trained models and checksum manifest (not committed)
app/            Preact + TypeScript + Vite frontend, served by the API
```

## Run it

From this folder, using the project's Python environment:

```powershell
..\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
```

Interactive API docs: <http://127.0.0.1:8000/docs>

On a fresh machine, install dependencies and set up first:

```powershell
python -m pip install -r requirements.txt
python -m scripts.seed
```

Run the tests (needs `requirements-dev.txt`):

```powershell
python -m pytest -q
```

## Frontend

The frontend is a static Preact app with no chart, CSS or router library. Visitors first see
a public landing page on pharmaceutical powder flow, with sources and a browser-only USP
calculator; the lab workspace requires sign-in. FastAPI serves it
from the same container, so it needs no second cloud service and no CORS setup. Filenames
are content-hashed and cached for a year, and responses are gzip-compressed.

For live frontend development, keep the API running on port 8000 and run:

```powershell
cd app
npm install
npm run dev
```

Then open <http://127.0.0.1:5173/>. Build for production with `npm run build`.

## Plans and payments (Razorpay)

| Plan | Price | Includes |
|---|---|---|
| Free | ₹0 | Exact USP classification, 20 results per month |
| Pro | ₹499 / 30 days | ML screening estimates, 500 results per month |
| Lab | ₹1,999 / 30 days | Unlimited results, personal activity log |

Each payment buys a 30-day pass through a Razorpay Order; nothing renews automatically.
Prices live only on the server (`api/billing.py`). A plan activates only after the payment
signature verifies and Razorpay confirms the captured amount. The webhook at
`/billing/webhook` (event `payment.captured`) is a backup if the browser closes early.
Reviewers and admins are never limited.

Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` in `.env`.
`rzp_test_` keys run test mode and `rzp_live_` keys take real money. Before going live,
complete Razorpay KYC and fill in the bracketed details in `app/src/content.ts`, which feed
the Terms, Privacy, Refund and Contact pages.

## Admin panel and superadmin

A separate admin-only app at `/admin` with overview, users, plan grants, subscriptions,
payments, profile-photo moderation and the audit trail. Non-admin accounts are refused by both
the panel and the API.

**Superadmin** is the highest role. It can also edit the public website (team members, the two
project guides, their photos, and the business details on the legal pages) under
**Admin > Site content**, and is the only role that can manage superadmin accounts. Create the
first one on the server with `python -m scripts.make_superadmin EMAIL`.

## Photo security

- **Profile photos are locked by default**, like a locked social-media profile: only the owner
  and administrators can see them. The owner can unlock under **My account**.
- Every upload is limited to 5 MB, checked by its real file signature (JPEG, PNG, WebP only),
  rejected if it is too large in pixels or animated, then **re-encoded** to a fresh square WebP.
  That removes location, camera and other hidden data, and neutralises disguised files.
- Files get random names and are stored privately (Amazon S3 with public access blocked, or the
  server's data volume). They are never public links: the API checks who is asking every time,
  and anyone without access gets "not found".
- Image responses cannot run scripts, are not cached for private photos, and cannot be embedded
  by other websites. Uploads are rate-limited and recorded in the audit trail.
- Right-click saving and dragging are blocked, but no website can stop screenshots.

## Amazon RDS PostgreSQL

Set `FLOWTOOL_DATABASE_URL` to the RDS endpoint, for example
`postgresql+psycopg://USER:PASSWORD@HOST:5432/powderflow?sslmode=require`. Tables and the
integrity triggers are created on first start. To copy existing data into an empty RDS
database:

```powershell
python -m scripts.migrate_sqlite_to_postgres data/app/flowtool.db
```

Run the whole test suite on PostgreSQL by setting `TEST_DATABASE_URL` to an empty test
database (it is wiped for every test).

## Deploy on AWS

Step-by-step guide and scripts: [deployment/aws/README.md](deployment/aws/README.md).
One EC2 server with Caddy HTTPS on the Elastic IP, Amazon RDS PostgreSQL, and the image in
private ECR.

## Run with Docker

Docker Desktop must be running. From this folder (`.env` must contain the signing key):

```powershell
docker compose up -d --build
```

Open the app at <http://127.0.0.1:8000/>. Interactive API docs are off in production mode.

```powershell
docker compose logs -f api
```

```powershell
docker compose down
```

`docker compose down` keeps your data in the `api-data` volume. Adding `-v` **permanently
deletes the database**. The container runs as a non-root user on a read-only filesystem and
is reachable only from this computer. The image contains the trained models, so build it
from a folder that has them in `models/`.

## Roles

| Role | Can |
|---|---|
| `analyst` | record samples, classify, see **own** records |
| `reviewer` | the above, see all records, review results produced by someone else |
| `admin` | the above, manage users, read the audit log |

## Endpoints

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/health`, `/ready` | public | liveness and database readiness |
| GET | `/model-card` | public | validation record of every tier |
| POST | `/auth/login` | public | get a bearer token (locks after repeated failures) |
| GET | `/auth/me` | any | current user |
| POST | `/auth/change-password` | any | change password and revoke old tokens |
| POST | `/classify` | any | classify supplied measurements |
| GET, POST | `/samples` | any | list or record measurements |
| GET | `/samples/{id}` | any | one sample |
| POST | `/samples/{id}/classify` | any | classify exactly what was recorded |
| POST | `/samples/{id}/void` | any | void with a reason (never deleted) |
| GET | `/materials` | any | list materials |
| GET | `/predictions`, `/predictions/{id}` | any | result history |
| POST | `/predictions/{id}/review` | reviewer, admin | one independent review |
| GET, POST | `/users` | admin | list or create users |
| PATCH | `/users/{id}` | admin | change name, role, status or password |
| GET | `/audit` | admin | append-only audit trail |

## Data integrity

- Audit entries cannot be changed or deleted, enforced in the ORM and by SQLite triggers.
- Prediction results and sample measurements are frozen once written.
- A result can be reviewed once, and never by the person who produced it.
- Model files load only if their SHA-256 matches `models/manifest.json`, through a class
  allowlist. After retraining with `python -m scripts.train`, the manifest is rebuilt.
- Secrets live in `.env`, which must never be committed.

## Known limitations

- Trained on a compiled secondary dataset, with no independent experimental validation.
- In that dataset, the reported Carr's index disagrees with the value recomputed from
  densities in 558 of 600 rows, although only 4 target labels change.
- Blend prediction is not implemented, because no blend data exists yet.
- Sign-up does not verify email addresses.
- Team names, photos and the business details on the legal pages are placeholders in
  `app/src/content.ts`.
