# WakaTime profile card

The README embeds local SVGs for GitHub's light and dark themes. The workflow updates them on every push to `main`, daily at 00:00 Asia/Qyzylorda (19:00 UTC the previous day), or manually from Actions → WakaTime profile → Run workflow. GitHub may delay scheduled runs; midnight is the scheduled time, not a guaranteed execution time. Commits created with the workflow's `GITHUB_TOKEN` do not trigger another push run. No image hosting service is required.

## Authentication

Reading statistics requires a personal OAuth token with the `read_stats` scope. Plugin API keys are write-only and cannot read statistics. Follow the personal-token link in the [authentication docs](https://wakatime.com/developers/#authentication), then add a repository Actions secret named `WAKATIME_TOKEN` in [Settings → Secrets and variables → Actions](https://github.com/rybk4/rybk4/settings/secrets/actions). The token takes priority over the older `WAKATIME_API_KEY` secret; the older name also accepts OAuth tokens for compatibility. Do not put credentials in the README or assets.

If daily runs fail with HTTP 401 or 403 in **Generate cards**, replace the token and verify its `read_stats` scope. The schedule cannot repair an authentication failure. After saving the secret, run **Actions → WakaTime profile → Run workflow** to verify both generation and the bot commit.

API reference: <https://wakatime.com/developers/#stats>.
Endpoint: `GET https://api.wakatime.com/api/v1/users/current/stats/last_30_days`.

The generated cards show the period, total time, average time per calendar day, and the number of days with recorded activity. Total time includes all tracked activity. The average divides that time by the number of calendar days and rounds to the nearest minute. If the API fails or is still calculating stats after retries, the workflow retains the previous cards.

## Local preview

Python 3.12+; no packages required:

```sh
python .github/scripts/wakatime.py --input .github/scripts/initial-stats.json
python -m unittest discover -s .github/scripts -p 'test_*.py'
```

`initial-stats.json` is a snapshot from 28 Sep–28 Oct 2026. The snapshot contains total time but no active day count, so the preview shows a dash for that metric. Workflow runs populate it from current API statistics.

The workflow needs repository contents write permission. If branch protection blocks direct bot pushes, allow the workflow through the repository's normal rules or adapt the commit step to your PR process.
