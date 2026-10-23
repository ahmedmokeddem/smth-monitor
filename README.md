# ARPEJ monitor — GitHub Actions + Discord

## Installation

1. Create a **public** GitHub repository, e.g. `arpej-monitor`. Public repos have free standard GitHub-hosted Actions runners. The repo and `state.json` will be public; the Discord secret will not.
2. Upload `monitor.py`, `requirements.txt` and `.github/workflows/monitor.yml` on the default `main` branch.
3. Discord: Channel Settings → Integrations → Webhooks → New Webhook → Copy Webhook URL.
4. GitHub: Settings → Secrets and variables → Actions → New repository secret. Name: `DISCORD_WEBHOOK_URL`. Value: your Discord webhook URL.
5. GitHub: Settings → Actions → General → Workflow permissions → **Read and write permissions**, if available.
6. GitHub: Actions → ARPEJ monitoring → Run workflow. Check logs. First scan creates `state.json` without notifications.
7. Subsequent scheduled runs compare `available` counts and alert on an increase.

## Schedule

The YAML cron `7,22,37,52 * * * *` runs around every 15 minutes UTC. For every 5 minutes use `7-59/5 * * * *` (executes :07, :12, ..., :57). GitHub scheduling is best effort, not guaranteed exact.

## Important limitations

**The parser is a first version, not live-tested against the site's raw HTML.** It detects nearby HTML text such as `complet` / `1 disponible` / `3 disponibles`. Check that the first Action log prints a plausible residence count. The source page returned through a web reading tool lists all 107 residences even with URL filters. Thus **do not assume the filtered city/audience is applied server-side** until checked using the browser and logs. If the filters are browser-side, adjust the scraping logic (e.g. use Playwright / inspect the network endpoint) before relying on notifications. Currently the script monitors all residences it can parse.

A GitHub public repository may have schedules automatically disabled after 60 days without qualifying activity; check its Actions status. Some scheduled jobs may be delayed/dropped. Do not share the webhook in source. Avoid heavy or aggressive scraping and respect site terms. If the page starts returning an error, the workflow fails and preserves state.
