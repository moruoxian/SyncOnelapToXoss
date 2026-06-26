# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Python tool that downloads cycling workout data from OneLap (顽鹿) and syncs it to multiple platforms: XOSS (行者), Giant (捷安特骑行), iGPSport, Garmin Connect China, and Strava. It also supports reverse incremental sync from iGPSport back to OneLap.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the full sync pipeline
python SyncOnelapToXoss.py

# Strava OAuth first-time authorization
python SyncOnelapToXoss.py --strava-auth

# Test Strava token validity
python SyncOnelapToXoss.py --strava-test

# Test upload a single FIT file to Strava
python SyncOnelapToXoss.py --strava-upload-test /path/to/file.fit

# Build Windows single-file executable
pyinstaller -F SyncOnelapToXoss.py --name SyncOnelapToXoss --noconfirm
```

There are no automated tests in this repository. Test scripts (`test_*.py`, `analyze_*.py`, `*_test.py`) are gitignored and used for ad-hoc debugging.

## Architecture

### Entry point and code organization

[SyncOnelapToXoss.py](SyncOnelapToXoss.py) (~3600 lines) is the **monolithic main script**. It contains all configuration loading, platform-specific login flows, API clients, and the 10-step sync pipeline inline at module level (no `main()` function wrapper — code after the function definitions runs directly at import time). The script is structured as:

1. **Module-level imports and constants** (lines 1–60)
2. **Config loading** via `configparser` from `settings.ini`, with fallback to hardcoded defaults (lines 66–229)
3. **Function definitions** — ~50 helper functions grouped by platform/responsibility (lines 248–3060)
4. **Inline execution flow** — steps 1–10 run sequentially at module level (lines 3053–3617), wrapped in a `try/finally` that ensures the browser tab and HTTP session are closed

[incremental_sync_v2.py](incremental_sync_v2.py) (~970 lines) is a **separate, self-contained module** for iGPSport → OneLap reverse sync. It defines two client classes and a coordinator:

- `IGPSportClient` — pure HTTP API client for iGPSport (login via REST, paginated activity listing, file download)
- `OneLapClient` — uses the OneLap signed API (same signature scheme as the main script) for listing and uploading FIT files
- `IncrementalSync` — orchestrates the reverse sync: compares iGPSport activities against OneLap's latest timestamp, downloads incremental files, and uploads them via OneLap's upload API

### 10-step sync pipeline (main script)

The main sync runs these steps sequentially:

1. **OneLap login** — browser-based login via DrissionPage (ChromiumPage), extracts `token` and cookies from the logged-in tab
2. **Baseline determination** — checks downstream platforms in priority order (XOSS → iGPSport → Giant → Garmin → Strava) to find the latest synced activity timestamp; this becomes the pagination stop marker for OneLap downloads
3. **FIT file download** — calls OneLap's signed paginated list API (`/api/otm/ride_record/list`), fetches detail for each record, downloads FIT via `/api/otm/ride_record/analysis/fit_content/{key}`, tracks completed downloads in `onelap_download_state.json`
4. **Upload to XOSS** — browser automation to XOSS file upload page
5. **Upload to Giant** — browser automation to Giant upload page
6. **Upload to iGPSport** — browser automation to iGPSport import page (file input + confirm button)
7. **Upload to Garmin Connect** — browser automation to `connect.garmin.cn/app/import-data`, handles CAPTCHA/2FA by allowing manual intervention
8. **Upload to Strava** — pure REST API upload via OAuth 2.0 tokens, with duplicate detection
9. **Verification** — checks latest activity times on XOSS/iGPSport/Garmin to confirm sync
10. **Reverse sync (iGPSport → OneLap)** — delegates to `IncrementalSync` from `incremental_sync_v2.py`

### OneLap API signing

The OneLap API uses a custom signature scheme. Key constants:

- Sign key: `fe9f8382418fcdeb136461cac6acae7b` (hardcoded in both scripts)
- Signing algorithm: `MD5(path + sorted query params + body JSON + signKey)`, communicated via `X-Sign` header
- Authentication: Bearer token obtained from browser cookies after login, sent as `X-Access-Token` header

Both `SyncOnelapToXoss.py` and `incremental_sync_v2.py` contain independent implementations of the signing functions (`rand_nonce`, `replace_empty_with_none`, `process_sign_params`, `generate_onelap_sign_headers`).

### Browser automation

The tool uses **DrissionPage** (not Selenium) to control a Chromium browser. The browser tab (`ChromiumPage`) is created once at startup and shared across all browser-based platform interactions. This means:

- The same `tab` object is passed to all `login_*_browser()` and `upload_files_to_*()` functions
- Platform HTML parsing uses a mix of DrissionPage's element selectors and BeautifulSoup
- Login flows include fallback selectors for UI variations (e.g., multiple selectors for login buttons, waiting strategies that check URL changes, DOM elements, and page titles)

### Configuration

`settings.ini` is the single config file, loaded from the script/program directory (not CWD). Template: `settings.ini.example`. Sections:

- `[app]` — log level, headless mode toggle
- `[onelap]`, `[xoss]`, `[giant]`, `[igpsport]`, `[garmin]` — per-platform credentials and `enable_sync` flags
- `[strava]` — OAuth 2.0 credentials (auto-written after first authorization)
- `[sync]` — storage directory, file format whitelist, max file size, batch size, `onelap_full_sync` flag
- `[igpsport_to_onelap]` — reverse sync toggle, mode (`auto`/`full`), strategy

### Packaging

GitHub Actions ([.github/workflows/build-release.yml](.github/workflows/build-release.yml)) builds Windows and Linux single-file executables via PyInstaller on push to `main`, `release-*` branches, or `v*` tags. The `v*` tag trigger also creates a GitHub Release.

### Docker

[Dockerfile](Dockerfile) provides a `selenium/standalone-chromium`-based image with Python and DrissionPage. It is a minimal container setup — not the primary deployment method.

### Important gitignore patterns

- `settings.local.ini`, `strava_upload_state.json`, `onelap_download_state.json` — contain real credentials/tokens, must not be committed
- `test_*.py`, `analyze_*.py`, `*_test.py` — ad-hoc test/debug scripts excluded from version control
- `downloads/`, `download_igps/`, `dist/`, `build/` — generated/transient directories

### Key dependencies

- **DrissionPage** (≥4.0.0) — Chromium browser automation (core runtime dependency)
- **requests** (≥2.25.0) — HTTP client with retry adapter for API calls
- **bs4** (BeautifulSoup) — HTML parsing for extracting activity data from platform pages
