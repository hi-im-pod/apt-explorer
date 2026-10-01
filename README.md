# APT Explorer

APT Explorer is a personal, non-commercial research project that tracks advanced persistent threat (APT) actors, the reports written about them, and recent reporting trends. It is built only from open sources, and the whole dataset can be rebuilt from them by one command.

The problem it addresses is naming. One vendor's APT28 is another's Fancy Bear, Sofacy or Sednit, so a search for one name misses reports filed under the others. The pipeline merges actor records from MITRE ATT&CK®, the MISP galaxy, ETDA's Threat Group Cards and Malpedia, and it keeps the evidence behind every merge so that a reader can check it. The site then lets a visitor find an actor, see each alias with the source that gives it, and read the reports linked to that actor.

The project is a showcase and possible thesis material. It is not a threat feed, and nothing on it is an attribution that I stand behind beyond what its sources say.

## The Three Stages

The project is built in three stages. This repository contains stage 1 only.

1. **Explorer.** A static site with a report and campaign explorer, actor profiles and current trends, built from structured open sources with no language model.
2. **Living dataset.** Language-model-assisted extraction from report text (victims, sectors, vectors, incident response detail), evaluated against labelled data. Nothing in stage 1 does this.
3. **Infrastructure pivoting.** Domains, IP addresses and file hashes extracted from reports and linked to actors over time, so that hunting can start from infrastructure reuse. This is the core research goal.

The data schema leaves room for stages 2 and 3, so they can be added as new pipeline steps and new site sections.

## How to Run It

The repository has two parts. The pipeline in `pipeline/` writes the dataset to `data/`. The site in `site/` reads that dataset and builds static pages.

### The Pipeline

The pipeline needs Python 3.12 or newer.

```sh
cd pipeline
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[test]"   # on Linux or macOS: .venv/bin/python

# Fetch every source and write data/. Each build reads the slug registry
# (data/slugs.json) that the previous one published, so actor addresses stay
# stable. Add --first-build only when starting a dataset from nothing.
.venv/Scripts/python -m aptx run --out ../data

# Rebuild from the snapshots already on disk, without touching the network.
.venv/Scripts/python -m aptx run --out ../data --skip-fetch

# Run the tests.
.venv/Scripts/python -m pytest -q
```

Raw source snapshots are kept in `.cache/snapshots/` at the repository root, which Git ignores. Set `APTX_CACHE` to keep them somewhere else. Snapshots hold report text that this project must not re-host, so they are never committed and never uploaded.

The weekly build keeps one small part of the snapshots elsewhere, because it cannot be fetched again. The blog feeds show only their newest posts, so the older titles, links and dates exist only in earlier snapshots, and the link check results take weeks to build up. `python -m aptx state pack` writes those two to an archive and `python -m aptx state unpack` restores them. Both refuse any other file, so no report text can enter the archive. The workflow stores the archive on a draft release of this repository, where an Actions cache eviction cannot reach it. Everything else stays in the cache, and losing it costs only a slow re-download.

A rebuild from the same snapshots is deterministic except for the build timestamps in `data/build.json`, `data/reports/index.json` and `data/trends.json`.

`python -m aptx links` checks the published report links that have waited longest since their last check. One run covers up to 8,000 links and at most 1,000 per host, sends no more than one request per second to any one host, and stops after 40 minutes. The results carry over between runs, so the whole list is covered over several weeks. The mirror of VX Underground holds about a third of all links and takes the longest. The link health shown on the site covers only the links checked so far.

### The Site

The site is SvelteKit with the static adapter. It needs Node.js and npm.

```sh
cd site
npm ci
npm run dev                    # copies ../data first, then starts the dev server

BASE_PATH=/apt-explorer npm run build
BASE_PATH=/apt-explorer npm run preview    # open http://localhost:4173/apt-explorer/

npm test                       # unit tests
npm run check                  # type and Svelte checks
npm run test:e2e               # Playwright, builds and serves the site itself
```

The base path always comes from `BASE_PATH`, because GitHub Pages serves a project site under `/<repository>/` and the site may later move to a server under another prefix. The preview address needs its trailing slash. On Git Bash for Windows, prefix the commands with `MSYS2_ENV_CONV_EXCL=BASE_PATH` so that the shell does not rewrite the path.

The repository also holds a test workflow and a weekly build workflow in `.github/workflows/`. The weekly build runs on Mondays at 03:17 UTC. It refreshes the data inside the runner and deploys to GitHub Pages without committing anything. The repository variable `PUBLISH_ENABLED` gates the scheduled run and the deploy, and a manual run always builds.

## Sources and Licences

The project reads thirteen sources: MITRE ATT&CK®, the MISP galaxy threat-actor cluster, ETDA's Threat Group Cards, Malpedia, ORKL, the CISA Known Exploited Vulnerabilities Catalog, The DFIR Report, Microsoft Threat Intelligence's threat actor naming table, FIRST's Exploit Prediction Scoring System (EPSS), three vendor blogs (Cisco Talos, ESET's research posts and the Microsoft Security blog), and the dataset released with the paper credited below.

Each source has its own licence, and the licence decides what the site may publish from it. [SOURCES.md](SOURCES.md) quotes every licence, records the decision for each source, and is the authority for the policy in code. In short:

- **Published in full:** MITRE ATT&CK®, the MISP galaxy, the CISA KEV catalog, Microsoft's threat actor naming table, FIRST's EPSS scores and the paper's dataset.
- **Published as derived facts only:** ETDA and Malpedia. Normalized names and values appear, and their descriptive text does not.
- **Linked to, not copied:** ORKL, The DFIR Report and the three vendor blogs. The site shows a report's own title, publication date and original URL. ORKL's permission request is still pending, and its actor tags are used only as matching evidence and never shown. When a vendor blog's title names an actor that has a page here, the report is also linked to that actor, and the site lists that link apart from the tagged ones. ORKL's titles are not read for this.

Because ETDA and Malpedia are share-alike, the files in `data/` are offered under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). `data/NOTICE.md` carries the attribution for every source, including MITRE's copyright designation. The code in `pipeline/` and `site/` is released under the [MIT licence](LICENSE), which does not apply to `data/`. The fonts, Mona Sans and Martian Mono, are installed from Fontsource under the SIL Open Font License 1.1.

Reports belong to their authors. The site never re-hosts a report's text or PDF.

## Credit

This project builds on the work of Yuldoshkhujaev, Jeon, Kim, Nikiforakis and Koo, *A Decade-long Landscape of Advanced Persistent Threats: Longitudinal Analysis and Global Trends*, published at the 2025 ACM SIGSAC Conference on Computer and Communications Security (CCS '25). The preprint is on [arXiv (2509.07457)](https://arxiv.org/abs/2509.07457). The first author is a colleague in my lab, and I am grateful for the dataset.

The authors released their data on [Zenodo (record 16869733)](https://doi.org/10.5281/zenodo.16869733) under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). APT Explorer uses it as one labelled historical input. No view reproduces a figure from the paper. The attribution that the licence requires is:

> Data from Yuldoshkhujaev, S., Jeon, M., Kim, D., Nikiforakis, N., Koo, H. A Decade-long Landscape of Advanced Persistent Threats: Longitudinal Analysis and Global Trends. Proceedings of the 2025 ACM SIGSAC Conference on Computer and Communications Security (CCS '25). Dataset: https://doi.org/10.5281/zenodo.16869733, licensed under CC BY 4.0, https://creativecommons.org/licenses/by/4.0/. Modified: rows were parsed, split and filtered by apt-explorer.

## Related Work

[APT Map](https://lngt-apt-study-map.vercel.app/) is an interactive map of hand-curated incident rows built from the same paper dataset. It shows incidents from the victim's side or the attacker's side, filters them by year, country and actor, and gives each incident a detail panel with the CVE, zero-day use, source, attack vector, malware, sectors and duration. Community additions are made by GitHub pull request. APT Explorer answers a different question: it is an explorer of actors and of the reports written about them, with a pipeline that can be rebuilt from open sources. The map's code is in [SecAI-Lab/APTMap-backend](https://github.com/SecAI-Lab/APTMap-backend) and the dataset repository is [SecAI-Lab/A-Decade-long-Landscape-of-Advanced-Persistent-Threats](https://github.com/SecAI-Lab/A-Decade-long-Landscape-of-Advanced-Persistent-Threats).

## Known Limitations

- **Report dates have different bases.** A date can come from the Malpedia library, from a date in the report's own title, from the report file's metadata, from the paper's dataset, or from the day ORKL ingested the report. The last one is when ORKL saw the report, not when it was published. Every weekly build changes how many reports carry that ingest date, because ORKL adds reports faster than other sources date them. Each report records its basis, and a report with no usable date is kept out of the dated trends.
- **Some sources give evidence only.** ETDA and Malpedia contribute names and values but no descriptive text, and ORKL, The DFIR Report and the three vendor blogs contribute links and metadata only. ETDA has not updated its data since 16 August 2025, and the source health panel says so.
- **A title can name an actor in passing.** The vendor blogs keep no post text, so the only evidence they give is the title. The matcher reads whole words, skips names that two actors share, skips ordinary words and malware names, and lists its links separately as "Named in the title". It still misses actors that a title does not name, and it can link a report that only mentions an actor. In an offline test on 29,263 ORKL titles in October 2026, 83% of the matches agreed with the report's own Malpedia or ATT&CK tag. The rest were mostly correct names that the tags leave out, and I count them as a lower bound on precision.
- **The guesses are pending and scored.** Some names in the paper's reports match no actor in the registry. The Name Guesses page labels each one (actor, malware, tool or not an entity) and names the closest known actor, under the heading "pending confirmation". No guess changes an actor, an alias or a report link. To measure the method, I hide each known name in turn and ask it to recover the label, then compare it with a version that uses only the shape of the name and with always answering "actor". The Name Guesses page shows the current scores. The gap over those baselines is small and every guess falls in the low confidence band, so I treat the guesses as leads and not as findings.
- **There are no per-campaign victims yet.** No current structured source gives victim country or sector per report. The site shows the countries that ETDA claims for an actor, and the sectors that ETDA, MISP and Malpedia claim, as a whole and labelled as such. Per-campaign victims wait for stage 2.
- **The merge is only as good as the aliases.** The Methodology page gives the share of the paper's actor names that the registry resolves. That rate measures agreement with the paper's labels, not correctness. A name carried by two ATT&CK groups is never used to merge them, and the Methodology page lists every such alias.
- **Report links are checked in rotation.** Each weekly run checks the links that have waited longest, so coverage grows over several weeks, a status can be a few weeks old, and a link that no run has reached yet shows no status. A report may link to an archive or a mirror copy next to the original publisher's page, and the report panel says which is which.
- **The trends cover recent reporting only.** The recent window reaches back 24 months (`WINDOW_MONTHS` in `pipeline/aptx/build/trends.py`), rounded down to the start of a quarter, and the Trends page states the date it starts. The paper covers 2014 to 2023 and is used as history, not as a trend source.
