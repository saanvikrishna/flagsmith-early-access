PYTHON ?= python3
REPO ?=

.PHONY: help test lint seed-dry up down tui harness-offline harness-live

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

test: ## Run all Python, demo-app, and VS Code extension unit tests
	@for dir in demo-seed harness self-hosted tui; do \
		$(PYTHON) -m unittest discover -s "$$dir" -p "test_*.py" -v; \
	done
	cd demo-app && npm test
	node --test vscode-extension/test/extension.test.js

lint: ## Validate SKILL.md frontmatter/word budget and shellcheck helper scripts
	@$(PYTHON) -c 'import re; text = open("skill/flagsmith-early-access/SKILL.md", encoding="utf-8").read(); m = re.match(r"^---\n(.*?)\n---\n", text, re.S); assert m, "Missing YAML frontmatter"; fm = m.group(1); assert re.search(r"^name:\s*flagsmith-early-access\s*$$", fm, re.M); assert re.search(r"^description:\s*.+$$", fm, re.M); words = len(text.split()); print(f"SKILL.md word count: {words}"); assert words <= 2000, f"Exceeds 2000 words: {words}"'
	shellcheck skill/flagsmith-early-access/scripts/*.sh harness/fake_cli/flagsmith harness/fake_cli/gh harness/fault/flagsmith
	$(PYTHON) harness/check_readme.py

seed-dry: ## Preview Flagsmith and GitHub seed actions without writing
	$(PYTHON) demo-seed/seed_flagsmith.py --dry-run
	$(if $(REPO),$(PYTHON) demo-seed/seed_issues.py --repo $(REPO) --dry-run,)

up: ## Start self-hosted Flagsmith and demo-app stack
	bash self-hosted/up.sh

down: ## Stop self-hosted Flagsmith and demo-app stack
	docker compose down

tui: ## Launch the zero-dependency early-access terminal dashboard
	$(PYTHON) tui/ea_dashboard.py

harness-offline: ## Run ea.sh integration tests against the stateful fake CLI (fault injection)
	$(PYTHON) -m unittest harness/test_ea.py -v

harness-live: ## Live skill-vs-baseline benchmark (needs .env, GH_REPO, claude)
	$(PYTHON) harness/bench.py --scenarios S1,S2,S3,S4,S5 --baseline && $(PYTHON) harness/bench.py --report
