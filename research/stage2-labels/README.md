# Labelling Victims and Initial Access in Threat Reports with Local Language Models: A Pilot Study

Status: working paper, 2026-10-07. Results in Section 7.6 and the recommendation in Section 9 are filled from `data/scores.json`; every number in this document is recomputed by `code/rescore_all.py` from the files in `data/`.

## Abstract

APT Explorer links threat intelligence reports to the actors they describe, but it cannot yet say who a report's victims were or how the attackers got in. We study whether a language model running on one consumer GPU can extract four facts per report: victim countries (or regions), target sectors, whether private individuals were targeted, and the initial-access technique. We first measured a hosted model (Claude Haiku 4.5) against the per-report labels released with the CCS '25 APT dataset [1] and found that model F1 stalls between 0.65 and 0.74 for every prompt we tried. Two prompts agreed with each other at about the same level as each agreed with the labels, which shows that the reference labels, not the model, set the ceiling. We therefore replaced the paper's three ad hoc label lists with published standards (MITRE ATT&CK Initial Access [2], the STIX 2.1 industry-sector vocabulary [3] and UN M49 regions [4]) and written rules. Against the paper's labels mapped onto the new scheme, the hosted model rose to 0.82 (countries), 0.73 (sectors) and 0.84 (initial access), and a local mixture-of-experts model reached 0.80, 0.63 and 0.83. On a 60-report test set labelled independently by two local models and by Claude, the local models agreed with each other far more than with Claude; the gap traced to rules the models did not follow (expanding regions into countries, listing attacker countries) and to rule choices that the project owner then settled. We report the label system, the test harness, every run, and the threats to validity, including what we got wrong along the way.

## 1. Introduction

Threat intelligence reports state who was attacked and how, but in prose. A structured record of victims and initial access per report would let the site answer questions such as "which actors targeted telecommunications in South-eastern Asia through exploited edge devices in the last two years". The CCS '25 study of APT reporting [1] released such labels for 1,509 reports, but its pipeline is not public and its labels stop in 2023. A living dataset needs extraction that runs every week on new reports, at no per-report cost, without storing report text (the project's licence position, Section 3).

The project owner chose to run extraction on a local model, because the hosted model cannot run on local hardware and because local inference keeps report text off third-party servers while one source's permission request is pending.

This study makes four contributions.

- We show that the released per-report labels are internally inconsistent enough to cap measured accuracy near 0.7 F1, and we quantify where (Section 7.1).
- We define a label system built on published standards, with written rules and a mapping back to the paper's labels (Section 4 and `../../docs/stage2-labels.md`).
- We release a test harness, a 60-report test set split into development and test halves, and the outputs and scores of every run, so the comparison can be repeated (Section 6, `code/`, `data/`).
- We compare a hosted model and five local models on a single 10 GB GPU and document the configuration that works best within that limit (Sections 7 and 9).

## 2. Background and Related Work

**APT report corpora.** The CCS '25 dataset [1] covers 2014 to 2023 and labels each report with victim countries, target sectors, attack vectors, malware and dates. APT Explorer already ingests its report list. ORKL is a public library of about 29,500 reports with extracted text, which APT Explorer reads through its API.

**Vocabularies.** MITRE ATT&CK [2] defines Initial Access (TA0001) as a tactic with eleven techniques and their sub-techniques in v19. STIX 2.1 [3] defines an open industry-sector vocabulary used across CTI sharing. UN M49 [4] defines world regions and sub-regions.

**Language models for CTI extraction.** Prior work has applied language models to extract entities, TTPs and indicators from CTI reports [CITATION NEEDED]. We have not yet surveyed this literature; positioning this study against it is open work (Section 10).

## 3. Problem Definition and Constraints

**Task.** Given one report's text and title, output: report type; victim countries; victim regions (only where no country is stated); target sectors; whether private individuals were targeted; and initial-access techniques.

**Constraints.**
- **No stored text.** Report text is fetched and held in memory only. Nothing derived from it except closed-vocabulary labels may be kept. This follows the project's SOURCES.md position for link-only sources.
- **Local inference.** One RTX 3080 (10 GB) with a Ryzen 7 5800X3D and 32 GB RAM, reached over Tailscale. Models must fit or offload to system RAM.
- **Untrusted input.** Report text may contain instructions aimed at the model. Outputs are constrained to a JSON schema with closed enumerations; the model has no tools.
- **Data cap.** The host uses a capped mobile connection, so model downloads are limited (Section 8).

## 4. Label System

The full rules are in `../../docs/stage2-labels.md` (v1) and `prompts/v3.txt` (current). Summary of v3:

| Field | Values | Key rules |
|---|---|---|
| report_type | campaign, malware-analysis, actor-profile, advisory, news, attribution, survey, methodology | Attribution, survey and methodology reports carry no victim labels |
| victim_countries | ISO 3166-1 alpha-2 (model sees country names) | Named, or specific evidence (local-language lures for a local audience, country-specific software, a country-only regulator); never attacker, infrastructure, vendor, sample-upload or lure-topic countries |
| victim_regions | UN M49 regions and sub-regions, plus Middle East and Worldwide | Only when no country is stated for those victims; never expanded into countries |
| target_sectors | STIX 2.1 industry-sector vocabulary (34 values) | Most specific value; `commercial` only alone |
| individuals_targeted | true or false | Private people targeted as people, not employees |
| initial_access | 15 ATT&CK v19 Initial Access IDs | A document or file that reached victims through an unstated channel is `T1566` |

The v3 rules came from four decisions by the project owner after the first test (Section 7.5): add regions instead of guessing countries; count countries implied by specific evidence; treat an unstated-channel document as phishing; add a report type and skip victim labels for non-campaign reports.

## 5. Data

| Set | Reports | Source of text | Reference labels | Used for |
|---|---|---|---|---|
| Spike A | 200 | ORKL | CCS '25 labels | Hosted model, prompts v1 and v2 |
| Spike B | first 100 of spike A | ORKL | CCS '25 labels, and mapped to the new scheme | Local models and the new label set |
| Test set | 60 | ORKL | Claude (in session), v1 then v3 rules | Three-labeller comparison, tuning, final scores |

**Selection.** Candidates are CCS '25 reports that are also in ORKL and carry at least one victim, sector or vector label (870 after title matching; 1,204 reports carry both sources in APT Explorer's data, but only 870 match the paper's CSV by normalised title). Spike A is a seeded shuffle of the candidates. The test set comes only from candidates outside spike A: 6 reports per year from 2014 to 2023, at most 4 per publisher (`code/legacy/select_testset.py`, `data/testset.json`).

**Split.** Test-set reports were picked round-robin by year, so odd positions form the development half and even positions the test half; both are stratified by year. Tuning uses the development half only.

## 6. Method

### 6.1 Models

| Model | Where | Size and quantisation | Notes |
|---|---|---|---|
| Claude Haiku 4.5 | Anthropic API | closed weights | Spike A and B only |
| qwen3:8b | 3080 host, Ollama | 8B, Q4_K_M | Spike B |
| qwen3:14b | 3080 host | 14.8B, Q4_K_M; part in system RAM | Spike B |
| qwen3.5:35b | 3080 host | 35B MoE (about 3B active), Q4_K_M; experts in RAM | Spike B, test set |
| gemma4:12b | 3080 host | 11.9B, Q4_K_M | Test set |
| gemma4:26b | 3080 host | 25.2B, Q4_K_M | Test set (development half) |
| Claude (Opus, in session) | this session | closed weights | Test-set labels |

Candidate models were chosen with llmfit v1.1.16 [5] given the host's memory, then filtered by hand (Section 8).

### 6.2 Inference

Temperature 0. Local models run through Ollama's `/api/chat` with the JSON schema passed as `format`, thinking off unless stated, `num_ctx` 16,384 and the first 40,000 characters of the report. The hosted model used structured outputs (`output_config.format`) from Section 7.4 onward; earlier runs used forced tool calls, which did not enforce enumerations (Section 8). Each report is fetched from ORKL once per run, one second apart.

### 6.3 Post-processing

`harness.clean` maps country names to codes, intersects every list with its vocabulary, drops `commercial` when a specific sector is present, and clears victim fields for attribution, survey and methodology reports. The optional grounding step keeps a victim country only if the report text names it, by name, alias or demonym (`harness.named_countries`).

### 6.4 Metrics

Micro-averaged precision, recall and F1 per field over all labels in the evaluated reports (`harness.prf`). Sectors are also scored at the parent level (all `government-*` and `emergency-services` count as `government`), and initial access at the technique level (`T1566.002` counts as `T1566`). **Location** treats countries and regions as one set, so a correct region counts when the reference has no country. Report type and individuals are scored as accuracy.

### 6.5 Reference labels

For the spikes the reference is the CCS '25 labels, mapped onto the new scheme for Section 7.4 (mapping in `docs/stage2-labels.md` Section 5). For the test set the reference is Claude's labels, made in this session by reading a prose-only rendering of each report (code, indicator and hash lines removed, at most 24,000 characters at first, later 14,000 to 18,000). Claude labelled before seeing any model output for that report. The reference is provisional until the project owner adjudicates it (Section 10).

## 7. Experiments and Results

### 7.1 The hosted model against the paper's labels (spike A, 200 reports)

| Prompt | Countries P / R / F1 | Sectors F1 | Vectors F1 | Cost |
|---|---|---|---|---|
| v1, plain | 0.68 / 0.82 / 0.74 | 0.65 | 0.69 | $1.67 |
| v2, definitions and label caps | 0.77 / 0.69 / 0.73 | 0.67 | 0.68 | $1.77 |

Prompt v2 traded recall for precision without moving F1. v1 and v2 agreed with each other at F1 0.80 (countries), 0.71 (sectors) and 0.75 (vectors), about the level each reached against the paper. Per-label analysis showed why: "Corporations and Businesses" appears on 73% of Manufacturing reports; Spear Phishing and Malicious Documents co-occur on 59% of reports that carry either; the two prompts agreed on "Phishing" only 18% of the time; reports average 3.9 victim countries.

Cost was about $8.40 per 1,000 reports (mean 7,800 input tokens per report).

### 7.2 Local models against the paper's labels (spike B, 100 reports)

| Model and setting | Countries | Sectors | Vectors | Seconds per report |
|---|---|---|---|---|
| Haiku 4.5, v1 | 0.81 | 0.69 | 0.68 | about 4 |
| qwen3:8b | 0.46 | 0.51 | 0.55 | 6.4 |
| qwen3:14b | 0.46 | 0.54 | 0.59 | 21.0 |
| qwen3.5:35b, country codes | 0.51 | 0.51 | 0.58 | 13.6 |
| qwen3.5:35b, country names | 0.68 | 0.49 | 0.57 | 13.6 |
| qwen3.5:35b, country names, prompt v2 | 0.59 | 0.65 | 0.63 | 12.0 |

The jump from 0.51 to 0.68 came from fixing our own schema (Section 8, item 4), not from the model.

### 7.3 Picking local candidates

llmfit [5] listed models that fit 10 GB of VRAM and 32 GB of RAM. Its overall score favours small fast models, so we filtered for the largest models with an Ollama build: `qwen3.5:35b` (MoE, rated Good with experts in RAM) and `gemma4:12b` (rated Marginal). Its speed estimates used the wrong GPU (Section 8, item 9).

### 7.4 The new label set (spike B, 100 reports, scored against the mapped paper labels)

| Model | Countries | Sectors | Initial access (family) |
|---|---|---|---|
| Haiku 4.5 (structured outputs) | 0.82 | 0.73 | 0.84 |
| qwen3.5:35b | 0.80 | 0.63 | 0.83 |

Separating delivery from payload raised initial-access agreement from about 0.68 to 0.84. The two models disagreed on 45% of labels.

### 7.5 Three labellers on the test set (v1 rules, 59 reports)

| Pair | Countries | Sectors (parent) | Initial access (parent) |
|---|---|---|---|
| qwen3.5:35b vs gemma4:12b | 0.82 | 0.67 | 0.78 |
| Claude vs qwen3.5:35b | 0.38 | 0.54 | 0.67 |
| Claude vs gemma4:12b | 0.40 | 0.54 | 0.63 |

The two local models averaged 3.3 victim countries per report; Claude averaged 0.9. The models expanded regions ("Eastern Europe" became 13 countries; one report received 25) and listed attacker countries; Claude left initial access empty on 28 reports where the delivery channel was not stated, the models on 7 or 8. Keeping only countries named in the text raised agreement with Claude to 0.49 (qwen) and 0.47 (gemma). These findings led to the v3 decisions in Section 4.

### 7.6 v3 rules and model optimisation

**Full test set, v3 rules, no tuning (60 reports; reference Claude v3).** gemma4:12b scored location 0.50, regions 0.67, sectors (parent) 0.63, initial access (parent) 0.72 and report type 0.73, at 5.0 seconds per report. qwen3.5:35b scored 0.42, 0.28, 0.56, 0.79 and 0.62, at 11.8 seconds. Against v1, Gemma's initial-access agreement with Claude rose from 0.63 to 0.72, which shows the unstated-channel rule (Section 4) resolved most of that disagreement.

**Tuning on the development half (29 or 30 reports).** We compared prompt, schema, context and model changes for gemma4:12b, and two alternatives, with a composite score: the mean of location F1, sector F1 (parent), initial-access F1 (parent) and report-type accuracy.

| Configuration (development half) | Location | Sectors (parent) | Access (parent) | Report type | Composite | Seconds per report | Failed |
|---|---|---|---|---|---|---|---|
| gemma4:12b, v3 | 0.48 | 0.65 | 0.64 | 0.72 | 0.623 | 5.0 | 1 |
| **gemma4:12b, v3 + grounding** | **0.61** | **0.65** | **0.64** | **0.72** | **0.655** | **4.8** | 1 |
| gemma4:12b, v4 (worked examples) | 0.55 | 0.62 | 0.58 | 0.72 | 0.617 | 5.4 | 1 |
| gemma4:12b, v4 + decoy fields | 0.56 | 0.49 | 0.54 | 0.70 | 0.574 | 6.0 | 3 |
| gemma4:12b, v4 + decoy + grounding | 0.64 | 0.50 | 0.56 | 0.72 | 0.607 | 5.5 | 1 |
| gemma4:12b, v3 + grounding, 32K context, 100,000 characters | 0.47 | 0.70 | 0.65 | 0.70 | 0.630 | 6.2 | 0 |
| gemma4:12b, v3 + grounding, thinking on (4,000-token budget) | 0.63 | 0.56 | 0.79 | 0.84 | 0.704 on 19 reports | 27.8 | 11 |
| gemma4:26b, v3 + grounding | 0.62 | 0.54 | 0.66 | 0.76 | 0.645 | 10.3 | 1 |
| qwen3.5:35b, v3 | 0.74 | 0.59 | 0.74 | 0.43 | 0.624 | 11.6 | 0 |
| qwen3.5:35b, v3 + grounding | 0.65 | 0.59 | 0.74 | 0.43 | 0.603 | 11.7 | 0 |

Findings on the development half:
- **Grounding is the one change that helps Gemma without a cost.** Country F1 rose from 0.48 to 0.64. It hurt qwen (0.79 to 0.72), because qwen more often found countries the v3 rules allow by implication, which grounding removes when the country is not named.
- **Worked examples and decoy fields did not help.** Both cost sector accuracy, and decoy fields raised parse failures.
- **A longer context helps sectors and regions but hurts countries.** More text means more countries mentioned and listed.
- **The larger Gemma (26B) did not beat the 12B** and took twice as long.
- **Thinking mode looked best on the reports where it worked, but failed on 11 of 30**: the reasoning used the output budget and the answer came back empty. Its score is on the 19 successes only, which are likely the easier reports. Doubling the output budget to 8,000 tokens changed nothing: the same 11 reports failed and the other 19 received identical labels, at about 83 seconds per report including failures. The failures are therefore an incompatibility between thinking and schema-constrained output for this model in Ollama, not a budget limit.
- **Grounding as a post-processing step gives the same result as grounding inside the run** (composite 0.655 both ways), so it can be applied to any saved run.

**Selection.** We selected gemma4:12b with prompt v3 and grounding, the best composite among configurations that completed every report, and carried it and the strongest alternative to the test half without further changes.

**Held-out test half (30 reports).**

| Configuration (test half) | Country | Region | Location | Sectors (parent) | Access (parent) | Report type | Individuals | Composite | Seconds per report |
|---|---|---|---|---|---|---|---|---|---|
| **gemma4:12b, v3 + grounding** | 0.47 | 0.74 | **0.52** | **0.61** | 0.82 | 0.73 | 0.97 | **0.669** | **4.9** |
| gemma4:12b, v3 | 0.46 | 0.74 | 0.51 | 0.61 | 0.82 | 0.73 | 0.97 | 0.667 | 4.9 |
| qwen3.5:35b, v3 + grounding | 0.46 | 0.26 | 0.43 | 0.54 | **0.84** | **0.80** | 0.97 | 0.650 | 12.1 |
| qwen3.5:35b, v3 | 0.36 | 0.26 | 0.35 | 0.54 | 0.84 | 0.80 | 0.97 | 0.631 | 12.1 |

On the held-out half, Gemma with grounding leads on location, regions and sectors, qwen on initial access and report type, and Gemma is 2.5 times faster. The composite gap (0.019) is within the noise of 30 reports (Section 8, item 11), so the case for Gemma rests on speed and on matching qwen elsewhere, not on a clear accuracy lead. Country F1 near 0.47 against Claude remains the weakest result, and adjudication (Section 10) will show how much of that is the reference rather than the model.

### 7.7 Reproducibility and a Modelfile anomaly

**Determinism.** gemma4:12b with temperature 0 produced byte-identical raw output on the test half in three separate runs (the original v3 run and two re-runs, 30 of 30 reports each), so for this model the single-run scores are repeatable on this host. We did not repeat the qwen runs.

**A derived model behaves differently.** We built `aptx-labeler` from gemma4:12b with a Modelfile, first with the v3 prompt baked in as `SYSTEM`, then with only the parameters (`temperature 0`, `num_ctx 16384`, `num_predict 500`). In every variant it matched the base model on only 8 of 30 reports, failed to produce valid JSON on 4, and scored lower (composite 0.652 on 26 reports, against 0.669 on 30). Sending the prompt per request did not change this. The derived model kept the base model's renderer, parser and draft model, and both ran on the same loaded runner. We did not isolate the cause. The deployed setup therefore uses the base model with the prompt and settings sent in each request, which is exactly the configuration we measured, and the derived model was removed.

### 7.8 Comparison with the CCS '25 pipeline

**What the paper reports.** The CCS '25 authors extracted these fields with GPT-4-Turbo and checked its answers by hand on about 120 reports [1, Tables 4 and 5]: victim country P 0.88, R 0.86, F1 0.86; target sector P 0.82, R 0.89, F1 0.85; attack vector P 0.89, R 0.77, F1 0.83. Their questions carried no exclusion rules ("Which countries are being targeted?"), sectors and vectors were forced into 12 categories each [1, Table 9], and a false positive was an attribute "not present in the report". That is a presence check, not a role check: a country the report names as the attacker's or as a lure topic is present, so it would not count against the model.

**Why those numbers cannot be compared with ours directly.** Our reference is a different labeller (Claude, not a human), our rules are stricter (victims only, no region expansion, no attacker or lure countries), and our vocabularies are finer (34 sectors and 15 techniques against 12 and 12).

**A like-for-like comparison.** The paper's released labels are GPT-4-Turbo's output, and the test set carries them. We scored them, and our models, against the same reference on the same reports, after mapping our labels up to the paper's categories (`code/compare_paper.py`, `data/paper_comparison.json`).

| System (59 reports; reference Claude v3, paper categories) | Countries P / R / F1 | Sectors P / R / F1 | Vectors P / R / F1 |
|---|---|---|---|
| CCS '25 released labels (GPT-4-Turbo) | 0.34 / 0.59 / 0.43 | 0.49 / 0.77 / 0.60 | 0.66 / 0.89 / 0.76 |
| gemma4:12b, v3 + grounding | 0.38 / 0.80 / 0.52 | 0.56 / 0.84 / 0.67 | 0.67 / 0.89 / 0.76 |
| qwen3.5:35b, v3 | 0.30 / 0.88 / 0.44 | 0.60 / 0.60 / 0.60 | 0.80 / 0.87 / 0.84 |

On the held-out half alone (30 reports) the order is the same: the paper's labels score 0.39, 0.61 and 0.76, Gemma 0.47, 0.70 and 0.84.

**Reading this.** Under our rules, a local 12B model on a consumer GPU matches or exceeds the paper's GPT-4-Turbo output on all three fields. The comparison favours our models in one respect that matters: they were prompted with the rules the reference follows, and GPT-4-Turbo was not. What it shows is that our pipeline follows our stricter definition better than theirs does, not that it is more accurate than GPT-4-Turbo in general. The paper's labels have low country recall (0.59) as well as low precision (0.34): they miss victim countries the reference records, often ones implied by specific evidence, and list others that are not victims. Every system, ours included, still lists more countries than the reference (2.0 to 2.8 a report against 0.95), which is the main remaining error.

## 8. What Went Wrong, and What We Missed

We list every problem found during the study, including our own mistakes, because each one changes how the numbers should be read.

1. **Report text written to disk, then flagged by antivirus.** The first fetch script cached ORKL text in a scratch file. Windows Defender flagged it as `TrojanDownloader:Win32/AutoHK.E`, because some reports quote an AutoHotkey downloader. The file was deleted and every later script kept text in memory. Writing it at all broke the project's no-stored-text rule.
2. **Report text sent to a third-party API.** Spikes A and B sent ORKL text for 300 reports to Anthropic's API, at the owner's direction and behind the planned per-source switch, while ORKL's permission request was still pending. The production plan now keeps text local.
3. **Wrong ORKL endpoint.** The first fetch used `/library/entry/{id}` (HTTP 400). The correct path is `/library/entry/sha1/{id}`. Nothing was fetched until it was fixed.
4. **Country codes invented by the schema.** The first local runs constrained countries with a two-letter pattern. Models filled it with non-codes (`UW`, `EJ`, `PQ`) and `UK` for `GB`. Switching to an enumeration of country names lifted country F1 from 0.51 to 0.68. Earlier local scores understate the models.
5. **Unconstrained arrays ran away.** Free-text country strings ran until the output limit, producing broken JSON; a `num_predict` cap and enumerations fixed it.
6. **Off-vocabulary labels from the hosted model.** Forced tool calls did not enforce enumerations; Haiku returned 58 sector labels outside the list on 200 reports. Dropping them raised its sector F1 from 0.65 to 0.70, so Section 7.1 understates it.
7. **Inconsistent text length.** Haiku saw 60,000 characters, local models 40,000, and Claude a prose-only rendering of 14,000 to 24,000 characters. Long reports may name victims late; this favours Haiku in Section 7.2 and penalises Claude's reference.
8. **The reference is one AI labeller.** The test-set reference is Claude's labels, not a human's. Claude also drafted the guidelines, so the reference may share the guidelines' blind spots. Agreement with Claude is not accuracy.
9. **Hardware detection in llmfit.** llmfit ran on a different PC (GTX 1660 Super) with memory overridden, so its speed estimates use the wrong memory bandwidth.
10. **Leakage into the development of v3.** The v3 rules were written after reading all 60 test-set reports and the models' v1 outputs on them. Scores on the test half therefore measure rule-following on reports that shaped the rules. A fresh test set is needed for a clean estimate (Section 10).
11. **Small samples.** With 30 reports per half, scores swing between halves: qwen3.5 scored countries 0.79 on the development half and 0.44 over all 60. Differences under about 0.1 F1 are within noise.
12. **Single runs.** Most configurations ran once at temperature 0. Gemma 12B proved byte-for-byte repeatable over three runs (Section 7.7); the other models' repeatability is unmeasured.
13. **Grounding is approximate.** The demonym list covers 36 countries; implied countries (allowed by v3) are dropped by grounding when not named; a country named only in a URL or domain is not matched.
14. **Network failures counted as model failures.** ORKL fetch timeouts during a concurrent model download appear in the run files as failed reports (1 to 3 per run).
15. **Operational slips.** An Ollama download stalled and had to be restarted; an API key without a workspace scope failed until replaced; several shell commands lost variables to background jobs. None affected results, but each cost time.
16. **Data cost.** Model downloads (about 60 GB in total) used a large share of the host's mobile data cap. We did not test `qwen3.6:35b` (22.6 GB) for that reason.
17. **Period and language.** All test reports are from 2014 to 2023 and almost all in English. Accuracy on 2024 to 2026 reports, and on Korean, Chinese or Russian reports, is unmeasured.
18. **The paper's labels were never released with their guidelines.** Our mapping (Section 4) is our interpretation, so Section 7.4 compares schemes, not just models.

## 9. Recommendation and Deployment

**Model and settings.** gemma4:12b (Q4_K_M, 8.0 GB, already installed) called directly, prompt v3 sent with each request, JSON-schema output, temperature 0, `num_ctx` 16,384, the first 40,000 characters of each report, thinking off, then country grounding as post-processing. It labels a report in about 5 seconds on the RTX 3080, so a weekly run of about 300 new reports takes under 30 minutes, and the 60-report test set under 6 minutes. qwen3.5:35b is the fallback if initial access matters more than location; it can be swapped in with one argument.

**Not adopted:** worked examples and decoy fields (no gain), a 32K context (hurts countries), gemma4:26b (no gain, twice as slow), thinking mode (fails or is too slow at any budget we tried), qwen3.6:35b (not tested: 22.6 GB download on a capped connection, and its published gains are in agentic coding [7], not instruction following).

**Instructions built into the model: tested and not adopted.** Baking the prompt and settings into a named model with a Modelfile seemed the natural way to stop the rules drifting between runs. It changed the model's output and made it worse (Section 7.7), so the deployed setup sends the versioned prompt file (`prompts/v3.txt`) and the settings with every request instead, which gives the same protection against drift. `deploy/build_modelfile.py` and the two Modelfiles are kept as the record of that test.

**OpenClaude.** OpenClaude is a community fork of Claude Code's source, which leaked through npm source maps on 2026-03-31, with an adapter that lets it drive any OpenAI-compatible model, including Ollama [6]. We do not recommend it here, for three reasons:
- **Wrong tool.** It is an interactive coding agent. Extraction is one structured call per report, and an agent loop adds latency, tokens and failure modes without improving rule-following.
- **Provenance.** It is built from leaked proprietary source and exists in many unofficial forks. Depending on it in a public, MIT-licensed project invites licence questions.
- **Supply-chain risk.** Running an unofficial fork on a machine that processes malware reports widens the attack surface for no gain.

**Better ways to give the model instructions, in order of cost:**
- **Structured outputs and closed enumerations.** Already in use.
- **A Modelfile.** Tested; changed the output for the worse (Section 7.7).
- **Worked examples.** Prompt v4 adds four. They did not help on the development half (Section 7.6).
- **Decoy fields for non-victim countries.** Tested in Section 7.6.
- **A grounding pass.** Tested in Section 7.6.
- **Fine-tuning.** A small LoRA fine-tune on adjudicated labels needs a few hundred adjudicated reports first. This is the only option that changes the model rather than the prompt.

## 10. Limitations and Next Steps

- **Adjudication.** The project owner adjudicates the test-set disagreements; scores are then recomputed against the adjudicated reference.
- **A fresh, untouched test set.** About 60 reports from 2024 to 2026, labelled under v3 before any further tuning, to remove the leakage in Section 8, item 10.
- **The Modelfile anomaly.** Find out why a derived model diverges from its base (Section 7.7), for example by testing without the draft model.
- **Related work.** Survey language-model CTI extraction and position this study against it.
- **The remaining fields.** Indicators, malware and tools, techniques in prose, and incident tags (`docs/stage2-labels.md`, Section 7).

## Reproducing This Study

From the repository root, with `OLLAMA_HOST` pointing at an Ollama server that has the models:

```
python research/stage2-labels/code/harness.py run --model gemma4:12b --prompt v3 --variant ground --split all --out run.json
python research/stage2-labels/code/harness.py score --pred run.json --ref research/stage2-labels/data/runs/testset_claude_v3.json --split test
python research/stage2-labels/code/rescore_all.py
```

Prompts: `prompts/std-v1.txt` (Section 7.4), `prompts/v3.txt` and `prompts/v4.txt` (Section 7.6); the spike prompts v1 and v2 are inline in `code/legacy/spike_mem.py` and `code/legacy/spike_v2.py`. `code/legacy/` holds the exact scripts used for the spikes, with local paths replaced by environment variables. `data/spike/` holds their outputs (labels only), `data/runs/` every test-set run with per-report timing and token counts, and `data/scores.json` every score.

## References

[1] S. Yuldoshkhujaev, J. Jeon, D. Kim, N. Nikiforakis, and H. Koo, "A Decade-long Landscape of Advanced Persistent Threats," in *Proc. ACM CCS*, 2025. arXiv:2509.07457. Data: Zenodo 16869733.

[2] MITRE, "ATT&CK Enterprise, Initial Access (TA0001)," v19, 2025. https://attack.mitre.org/tactics/TA0001/

[3] OASIS, "STIX Version 2.1," OASIS Standard, 2021, Section 10.11 (Industry Sector Vocabulary). https://docs.oasis-open.org/cti/stix/v2.1/os/stix-v2.1-os.html

[4] United Nations Statistics Division, "Standard Country or Area Codes for Statistical Use (M49)."

[5] AlexsJones (GitHub), "llmfit," v1.1.16, 2026. https://github.com/AlexsJones/llmfit

[6] OpenClaude community forks, for example https://github.com/kevincodex1/openclaude (unofficial; accessed 2026-10-07).

[7] Qwen Team, "Qwen3.6-35B-A3B" model card, 2026. https://huggingface.co/Qwen/Qwen3.6-35B-A3B
