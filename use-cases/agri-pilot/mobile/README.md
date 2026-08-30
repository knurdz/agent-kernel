# AgriPilot Mobile (Android)

Android-only Flutter client for the AgriPilot backend in `use-cases/agri-pilot/`.

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
| Profile | `PATCH /api/auth/me` |
| WhatsApp / Telegram | `/api/auth/me/channels`, `/api/config/public` |

## Tests

```bash
flutter test
flutter analyze
```

## Production release (VPS)

Production uses HTTPS via Caddy on your VPS domain. **Do not** ship release APKs with `http://` base URLs.

```bash
flutter build apk --release --dart-define=API_BASE_URL=https://your-domain.example.com
```

Requirements:

- Backend deployed with `./deploy/deploy-vps.sh` (see parent [`README.md`](../README.md) "VPS deployment")
- DNS and TLS working (`https://your-domain.example.com/health` returns `{"status":"ok"}`)
- Cleartext HTTP is allowed only in **debug** builds (`network_security_config.xml`); release builds expect HTTPS

## Debug networking

Cleartext HTTP to `10.0.2.2` is allowed in debug builds via `android/app/src/debug/res/xml/network_security_config.xml`.
