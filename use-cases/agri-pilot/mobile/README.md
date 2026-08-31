<p align="center">
  <a href="../../README.md">
    <img src="../docs/branding/agripilot-icon.png" alt="AgriPilot logo" width="96" />
  </a>
</p>

<h2 align="center"><a href="../../README.md">AgriPilot</a> Mobile</h2>

<p align="center">
  Android Flutter client — AI chat, marketplace, and live delivery for the AgriPilot platform
</p>

<p align="center">
  <a href="../../README.md"><strong>Project README</strong></a>
  &nbsp;·&nbsp;
  <a href="https://github.com/yaalalabs/agent-kernel/releases?q=agripilot-mobile">Download APK</a>
  &nbsp;·&nbsp;
  <a href="#setup">Setup</a>
  &nbsp;·&nbsp;
  <a href="#production-release">Release</a>
</p>

---

Full project overview, architecture, VPS deployment, and API reference live in the repository [`README.md`](../../README.md).

## Prerequisites

- Flutter SDK 3.11+
- Android emulator or device
- Backend running at `http://localhost:8000` (Docker recommended)

## Setup

```bash
cd use-cases/agri-pilot
docker compose up --build   # Postgres + Redis + API on :8000

cd mobile
flutter pub get
```

## Run on emulator

The default API base URL targets the Android emulator host:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

For a physical device on the same LAN:

```bash
flutter run --dart-define=API_BASE_URL=http://<your-lan-ip>:8000
```

## Firebase (optional push)

1. Create a Firebase project and add an Android app (`com.example.mobile` — update `applicationId` in `android/app/build.gradle.kts` if needed).
2. Download `google-services.json` into `android/app/`.
3. Set on the backend: `AK_NOTIFICATIONS__FCM_ENABLED=true` and `AK_NOTIFICATIONS__FIREBASE_CREDENTIALS_PATH=/path/to/service-account.json`.

Without Firebase, the app runs normally; push registration is skipped.

## Features

| Screen | API |
|--------|-----|
| Login / Signup | `/api/auth/*` |
| Agent chat + photo | `POST /api/v1/chat`, `/api/v1/chat-multipart` (JWT) |
| Quick crop scan | `POST /api/farmer/scans` |
| My plants / plant detail | `/api/farmer/plants*` |
| Chat history | `GET /api/v1/threads*` |
| Farmer listings + import plant | `/api/farmer/listings`, `/api/farmer/listings/{id}/import-plant` |
| Buyer browse/match/connect + listing insights | `/api/buyer/*` |
| Connections + contact | `/api/*/connections*` |
| Rider jobs + live tracking | `/api/rider/*`, `/api/*/orders/{id}/tracking` |
| Profile | `PATCH /api/auth/me` |
| WhatsApp / Telegram | `/api/auth/me/channels`, `/api/config/public` |

## Tests

```bash
flutter test
flutter analyze
```

## Production release

Production uses HTTPS via Caddy on your VPS domain. **Do not** ship release APKs with `http://` base URLs.

### GitHub Actions (recommended)

1. Deploy the backend (see [`README.md`](../../README.md#production-vps-deployment))
2. Run **Actions → AgriPilot Mobile Release** with a `version` (e.g. `1.0.1`) and optional `api_base_url`
3. Edit the draft release notes on GitHub, then publish
4. Download the APK from [GitHub Releases](https://github.com/yaalalabs/agent-kernel/releases?q=agripilot-mobile)

### Local release build

```bash
flutter build apk --release --dart-define=API_BASE_URL=https://your-domain.example.com
```

Requirements:

- Backend deployed with `./deploy/deploy-vps.sh`
- DNS and TLS working (`https://your-domain.example.com/health` returns `{"status":"ok"}`)
- Cleartext HTTP is allowed only in **debug** builds; release builds expect HTTPS

## Debug networking

Cleartext HTTP to `10.0.2.2` is allowed in debug builds via `android/app/src/debug/res/xml/network_security_config.xml`.
