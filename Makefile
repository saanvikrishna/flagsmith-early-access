PYTHON ?= python3
REPO ?=

.PHONY: help test lint seed-dry up down tui harness-offline harness-live

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

test: ## Run all Python, demo-app, and VS Code extension unit tests
	@for dir in demo-seed skill/flagsmith-early-access/scripts harness self-hosted tui; do \
		$(PYTHON) -m unittest discover -s "$$dir" -p "test_*.py" -v; \
	done
	cd demo-app && npm test
	node --test vscode-extension/test/extension.test.js

lint: ## Validate SKILL.md frontmatter/word budget and shellcheck helper scripts
	@$(PYTHON) -c 'import re; text = open("skill/flagsmith-early-access/SKILL.md", encoding="utf-8").read(); m = re.match(r"^---\n(.*?)\n---\n", text, re.S); assert m, "Missing YAML frontmatter"; fm = m.group(1); assert re.search(r"^name:\s*flagsmith-early-access\s*$$", fm, re.M); assert re.search(r"^description:\s*.+$$", fm, re.M); words = len(text.split()); print(f"SKILL.md word count: {words}"); assert words <= 2000, f"Exceeds 2000 words: {words}"'
	shellcheck skill/flagsmith-early-access/scripts/*.sh

seed-dry: ## Preview Flagsmith and GitHub seed actions without writing
	$(PYTHON) demo-seed/seed_flagsmith.py --dry-run
	$(if $(REPO),$(PYTHON) demo-seed/seed_issues.py --repo $(REPO) --dry-run,)

up: ## Start self-hosted Flagsmith and demo-app stack
	bash self-hosted/up.sh

down: ## Stop self-hosted Flagsmith and demo-app stack
	docker compose down

tui: ## Launch the zero-dependency early-access terminal dashboard
	$(PYTHON) tui/ea_dashboard.py

harness-offline: ## Run the Offline Regression Suite (S1-S10 & X1-X5, 3 runs each)
	$(PYTHON) harness/run.py --runs 3 --baseline

harness-live: ## Run the scenario harness against live Flagsmith Cloud and GitHub
	$(PYTHON) harness/run.py --mode live --runs 3
