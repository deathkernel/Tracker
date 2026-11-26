# Capacitor native app setup

This repository is currently a Python/FastAPI server plus a single-file browser dashboard. Capacitor adds an Android/iOS project shell; it does not convert the Python backend into a mobile-native service.

## Prerequisites

- Node.js 20.0 or newer and npm
- Android Studio + Android SDK for Android builds
- macOS + Xcode for iOS builds

## Install and create native projects

```bash
npm install
npx cap add android
# On macOS only:
npx cap add ios
npm run cap:sync
npm run cap:open:android
```

The initial `www/` folder is a connection/setup screen. The existing dashboard still depends on the FastAPI backend and its SQLite database. The shell checks `/api/health` to help verify a host URL, but full dashboard embedding, authenticated remote API routing and QR-token handoff are not yet implemented.

## Important network note

The current Python server generates a short-lived bearer token for trusted-LAN phone access. A native client must securely obtain and send that token for all non-loopback `/api/*` calls. Do not disable the API guard or hardcode a token in the app. Use only a trusted private network.
