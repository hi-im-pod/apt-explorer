# Datasheet for APT Explorer

This datasheet follows the questions of Gebru et al., "Datasheets for Datasets" [1]. It describes the data in `data/`, which the pipeline rebuilds every week. The counts below come from the build of 2026-10-08T03:16:32Z, made by commit `f387067` in workflow run 37719073045. A frozen release replaces them with its own: `releases/<version>/MANIFEST.json` gives the counts and the SHA-256 of every file for that release, and it is the authority whenever it differs from this page.

Cite a frozen release by its version DOI, never the live site. Also cite the CCS '25 dataset [2] whenever you use its reports or labels. `CITATION.cff` gives both.

## Motivation

**Why was the dataset created?** Vendors name the same threat actor differently, so a search for one name misses reports filed under the others. APT Explorer merges actor records from four structured sources, keeps the evidence for every merge, and links public threat reports to the merged actors. It also extends the CCS '25 APT report dataset [2], which ends in 2023, with reports from later years.

**Who created it, and who funded it?** Garrett Ennis, a master's student in the SecAI Lab at Sungkyunkwan University, built it as a personal, non-commercial project. It has no funding, sponsor or commercial use.

**Relationship disclosure.** The CCS '25 dataset comes from the same lab. Its first author is a labmate, and the lab's director is a co-author. APT Explorer is the author's own work and has not been peer reviewed. The CCS '25 authors did not review it.

## Composition

**What do the instances represent?** Four kinds of record, each in its own file under `data/`:

| Record | Count | File |
|---|---|---|
| Threat report: a published document about an actor, campaign or tool | 24,608 | `reports/<year>.json`, `reports/undated.json`, `reports/index.json` |
| Actor: a merged threat actor | 1,098 | `actors/<id>.json`, `actors/index.json` |
| Campaign: an ATT&CK campaign | 59 | `campaigns.json` |
| Vulnerability: a CVE in CISA's KEV catalog or named in a report | 3,172 | `vulns.json` |

Other files hold trends (`trends.json`), name resolution statistics and ambiguities (`resolution.json`), the name guesser's output (`guesses.json`, `terms.json`), per-source health and licences (`sources.json`), frozen actor slugs (`slugs.json`), the build stamp (`build.json`) and attributions (`NOTICE.md`). JSON schemas for every file are in `pipeline/aptx/build/schemas/`.

**Where do the reports come from?** A report can come from several sources at once, so the counts overlap.

| Source | Reports | What it supplies |
|---|---|---|
| ORKL | 24,466 | Title, link, date evidence, and the text that the pipeline reads in memory |
| CCS '25 lab dataset [2] | 1,495 | Title, publisher, date, actor names, CVE and technique labels |
| The DFIR Report | 97 | Title, link, date, publisher |
| ESET, Cisco Talos and Microsoft Security blogs | 24, 19, 14 | Title, link, date, publisher |

Almost every report has an ORKL copy. ORKL's permission request was still pending when this datasheet was written, so ORKL is used under the `link-only` policy in `SOURCES.md`: titles, dates and links are published, and only identifiers the pipeline finds itself are taken from its text.

**What does each report record contain?** Coverage in the 2026-10-08 build:

| Field | Reports with a value | Share |
|---|---|---|
| Date | 24,608 | 100% |
| Publisher | 9,710 | 39% |
| At least one actor | 12,124 | 49% |
| An actor named in the title | 3,075 | 12% |
| An actor named in the text | 5,774 | 23% |
| At least one CVE | 3,633 | 15% |
| At least one ATT&CK technique | 2,533 | 10% |

**Is anything missing on purpose?** Yes. No report text, PDF or image is included, and nothing is re-hosted. ORKL's actor tags are never published. There are no network indicators, victim labels or incident narratives yet; the stage 2 study in `research/stage2-labels/` works toward victim and initial-access labels, but none are in `data/`.

**Is the dataset a sample?** It is not a complete record of APT reporting. It holds what ORKL, Malpedia, the lab dataset and four feeds index, which favours English-language reports from large vendors.

**Does it contain personal or confidential data?** No. Every record comes from public sources. Actor names are names of threat groups. A few publisher values are the names of report authors, as printed on public reports.

## Per-Field Provenance

Each report records which sources supplied it (`sources`). The table gives, for each field, where the value comes from and the rule that sets it.

| Field | Origin | Rule |
|---|---|---|
| `id` | A copy's SHA-1, else its source and source ID | The smallest SHA-1 among the copies; otherwise the first source's own ID |
| `merged_ids` | The pipeline | Every ID a copy would have on its own, when copies were joined |
| `title` | The first copy with a usable title | File-name titles are tidied; placeholders and error pages give way to another copy's title or the address; a site's name shared by four or more pages on one host is replaced by a title read from the address |
| `published`, `date_basis` | The best evidence among all copies | See Date Bases below |
| `organisation` (publisher) | A feed, a title, a source field, or the address | A publisher's own feed first; then a vendor blog named in any copy's title; then the copies' publisher fields (ORKL's only when it names a known vendor); then the publisher whose own site the original address is on. Spellings are made canonical |
| `url`, `archive_url` | The copies' links | An original publisher link is preferred to a mirror |
| `url_ok` | The pipeline's link checker | `true` or `false` for a checked link; `null` for one not yet checked |
| `actors` | Malpedia report links, ATT&CK group references, the lab dataset's actor names, titles and text | A Malpedia family's reports link to its actors only when Malpedia attributes the family to three names or fewer |
| `actors_from_title` | Matching the title against published actor names | Whole words; ambiguous and generic names skipped |
| `actors_from_text` | Matching ORKL's text in memory | A name used twice, or once in the first 300 words for a multi-word name or one with a digit |
| `actor_names_unresolved` | The lab dataset's actor names that match no actor | Kept verbatim |
| `cves` | The lab dataset's labels and CVE IDs written in the text | A CVE numbered more than a year after the report's date is dropped; nothing is read from an error page |
| `techniques` | The lab dataset's labels (158 reports) and technique IDs written in the text (the rest) | Only IDs in the current ATT&CK release are kept |
| `sources` | The pipeline | Every source that lists the report |

**Technique IDs are what the publisher wrote, not what the attack used.** Outside the 158 lab-labelled reports, a technique ID is present because the report's own text contains it, such as "T1566.001" in a mapping table. The pipeline infers no technique from prose. An ID may appear in detection guidance, an appendix or a general overview without describing the attack, and reports that never print IDs have none. Recall is low, and the set favours vendors that publish ATT&CK tables.

## Date Bases

Each report has one date and the basis it came from. The first rule that gives a usable date wins.

| Basis | Meaning | Reports | In trends |
|---|---|---|---|
| `publisher` | The publisher's own feed | 154 | Yes |
| `malpedia-library` | Malpedia's library entry, unless the address carries a date at least a year later | 11,179 | Yes |
| `paper` | The lab dataset | 1,019 | No: the lab corpus is a historical layer |
| `title-date` | A filing date at the start of the title, no later than ORKL's ingest | 5,754 | Yes |
| `url-date` | A date in a blog-style address, outside upload folders | 733 | Yes |
| `file-metadata` | The report file's creation date | 1,182 | Yes |
| `wayback-capture` | The day the Wayback Machine saved the page, an upper bound | 77 | No |
| `orkl-ingest` | The day ORKL added the report, often years late | 4,510 | No |

A study that needs publication dates should drop `orkl-ingest` and `wayback-capture`, as the trends do.

## Collection Process

The pipeline (`pipeline/aptx/`) fetches each source once a week through a scheduled GitHub Actions workflow, keeps the newest good snapshot of each, and rebuilds `data/` from the snapshots. A failed fetch falls back to the previous snapshot, and `sources.json` marks it stale. ORKL's text is read once, in memory, to find actor names and CVE and technique IDs; the text is never stored or published. A link checker visits up to 8,000 report links per run at one request per second per host. Snapshots are not published, because they hold report text this project may not re-host, so a third party cannot rebuild an exact release. The frozen release is the reproducible artifact.

## Cleaning and Merging

- **Actors.** Records from ATT&CK, the MISP galaxy, ETDA and Malpedia merge when they share a normalized name or alias. Each shared name is kept as an evidence edge. A name shared by two ATT&CK groups never merges them, and software names never become actors.
- **Copies of one report.** Copies merge when they share an address or a SHA-1, or when their tidied titles match, the title has at least 20 characters, and each copy is dated within 14 days of the one before it.
- **Publishers.** One canonical name per publisher (`pipeline/aptx/core/publishers.py`). The audit found 40 spelling groups; 3 remain in the 2026-10-08 build.
- **Trends.** Reports linked to 15 or more actors are left out of per-actor trends, and `trends.json` counts how many.

## Known Errors and Limitations

An outside audit of the 2026-10-02 build listed the problems below. Sizes are measured on the 2026-10-08 build unless stated.

| Problem | Size | Status |
|---|---|---|
| Ingest dates counted as publication dates | 5,448 reports in the audited build | Fixed for trends. 4,510 reports still have no better date; they are shown but left out of trends, timelines and new actors |
| Reports misdated by a wrong Malpedia year | 8 in the audited build | Fixed by the address-date override |
| Lab rows with another vendor as publisher | 20 checkable rows | 12 fixed in the 2026-10-08 build; a later rule (commit `9caa5e0`) covers the other merged copies and takes effect at the next build |
| Publisher missing | 14,898 reports (61%) | Partly addressed: blank publishers are filled only from sites a known publisher runs |
| Generic site titles and error-page titles | 609 and 20 in the audited build | Error pages: 0. Site names: retitled from the address where it has words |
| CVEs numbered after the report | 110 in the audited build | Fixed: 0 |
| Duplicate reports | 5,278 surplus copies in the audited build | 4,894 copies merged. 985 groups of reports still share a title: in 534 the dates are more than 14 days apart, 221 have titles under 20 characters, 10 are site names, and in the other 220 the copies' own dates are too far apart even though the reports' chosen dates are close |
| Lab and ORKL copies of one paper kept apart | 79 pairs in the audited build | 74 now one report |
| Reports linked to 15 or more actors | 717 in the audited build | 82, after shared malware families stopped linking all their users |
| Reports with 100 or more technique IDs | 11 | Not addressed; treat them as compendia |
| Broken links | 1,064 of 24,180 checked | Reported per link in `url_ok`; the link stays |
| Report IDs change between builds | Until commit `99cdd02`, a copy joined by a shared address lost its old ID (17 of the 79 lab and ORKL pairs) | Fixed at the next build: every copy's own ID resolves through `merged_ids` |

Further limits:

- **No measured error rates yet.** Every fix above was checked by rules and counts, not against a human-checked random sample. Read the table as known problems, not as an error bound.
- **The Malpedia cap counts names.** A family listed under four aliases of only two actors links to none of them.
- **Period and language.** Coverage after 2023 depends on ORKL and four feeds, and almost all reports are in English.
- **The live site changes weekly.** Only a frozen release is fixed.

## Uses

**Suitable:**

- Finding the public reports about an actor under any of its names, with the evidence for each link.
- A sampling frame of threat reports with a recorded date basis, after the filters below.
- Studying publisher-asserted ATT&CK mappings, as long as an ID's presence is not read as proof of use.

**Not suitable:**

- Attribution. A link means a source or a report names the actor, not that the attribution is correct.
- Ground truth for which techniques an attack used, without a human check against the report text.
- Commercial use, which the share-alike, non-commercial licence does not allow.

**Suggested filters for research use:**

- Drop reports whose `date_basis` is `orkl-ingest` or `wayback-capture`.
- Flag reports with 15 or more `actors` or 100 or more `techniques` as compendia.
- Resolve old IDs through `merged_ids` before joining with other data.
- Report results on the CCS '25 labels separately, and cite that dataset for them.

## Distribution

**Licence.** The data in `data/` is offered under CC BY-NC-SA 4.0, and the code under the MIT License. `SOURCES.md` quotes every source's licence and explains why one licence satisfies all of them, and `data/NOTICE.md` carries the attributions each source requires. Anyone who reuses `data/` must keep those attributions and the same licence.

**How a release is frozen.** The weekly build deploys without committing data, so a release is cut by hand:

1. Pick a successful build run and download its data artifact into `data/`, replacing the committed copy: `gh run download <run> -n data -D data`.
2. Freeze it: `python -m aptx.freeze --data ../data --version vX.Y.Z --commit <the run's commit> --run <run> --out ../releases/vX.Y.Z` from `pipeline/`. The command refuses a tree the pipeline would not publish.
3. Commit `data/` and `releases/vX.Y.Z/`, tag the commit `vX.Y.Z`, and publish a GitHub release. With the Zenodo integration switched on, Zenodo archives the release and mints a version DOI; `.zenodo.json` supplies its metadata.
4. Check the release with `sha256sum -c releases/vX.Y.Z/SHA256SUMS` from the repository root.

## Maintenance

Garrett Ennis maintains the dataset. The pipeline rebuilds the live data every Monday. Frozen releases never change; a correction ships as a new release with its own version DOI, and Zenodo's concept DOI points to all of them. Report errors through the repository's GitHub issues.

## References

[1] T. Gebru, J. Morgenstern, B. Vecchione, J. W. Vaughan, H. Wallach, H. Daumé III, and K. Crawford, "Datasheets for datasets," *Communications of the ACM*, vol. 64, no. 12, pp. 86–92, 2021, doi: 10.1145/3458723.

[2] S. Yuldoshkhujaev, M. Jeon, D. Kim, N. Nikiforakis, and H. Koo, "A decade-long landscape of advanced persistent threats: Longitudinal analysis and global trends," in *Proc. ACM SIGSAC Conf. Computer and Communications Security (CCS '25)*, 2025, doi: 10.1145/3719027.3765085. Dataset: Zenodo, doi: 10.5281/zenodo.16869733.
