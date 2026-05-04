# SaaSScout Launch Checklist

Use this before sharing the project link or recording a demo.

## Production Health

- Run `python scripts/production_monitor.py --site-url https://saas-intelligence-copilot-calvi.netlify.app --timeout 45 --retries 2 --retry-delay 8`.
- Confirm the GitHub Actions `Production Monitor` workflow has a recent passing run.
- Open `https://saas-intelligence-copilot-calvi.netlify.app` and verify the loading screen exits.
- Check `https://saas-intelligence-copilot-api.onrender.com/health` returns `{"status":"ok"}`.

## Demo Flow

- Run the support comparison prompt and confirm review snippets appear.
- Open the Scorecard tab and confirm pricing provenance is visible.
- Run the PM automation shortlist prompt and confirm FactGrid Enterprise Metadata and Vendor Facts render in the Evidence tab.
- Run the open-source alternatives prompt and confirm the Alternatives tab appears only for that query.

## Portfolio Assets

- Regenerate screenshots with `cd frontend && npm run capture:demo`.
- Confirm `docs/assets/saasscout-desktop.png`, `docs/assets/saasscout-mobile.png`, and `docs/assets/saasscout-evidence.png` are updated.
- Check README image rendering and Live Demo links on GitHub.
- Confirm screenshots do not show local URLs, secrets, browser extensions, or account-specific data.
