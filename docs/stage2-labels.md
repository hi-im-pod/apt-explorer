# Stage 2 Label System: Design and Labelling Guidelines

Status: v3, 2026-10-07. Nothing here is published on the site yet. The evaluation behind these rules, with every run and score, is in `research/stage2-labels/`.

## Changes in v3 (2026-10-07)

After the first three-labeller test, the project owner settled four rules. They override anything below that conflicts with them, and `research/stage2-labels/prompts/v3.txt` is the exact prompt.

1. **Regions instead of guessed countries.** A new `victim_regions` field (UN M49 regions and sub-regions, plus Middle East and Worldwide) is used only when the report places victims in a region without naming their countries. A region is never expanded into countries.
2. **Countries implied by specific evidence count.** For example: lures written in the victims' language for a local audience, software or security products specific to one country, a regulator or filing that applies only there, or the location of a named victim organisation. A country that is only the topic of a lure still does not count.
3. **A document that reached victims is initial access.** When a malicious document reached the victims and the report does not say how, record `T1566.001` (spearphishing attachment), the usual route for a document; record `T1566` only when phishing is stated without its channel and no document is involved (changed from `T1566` during adjudication on 2026-10-07, prompt v3.2). Mass malicious spam with attachments is `T1566.001`.
4. **Report type.** A new `report_type` field: campaign, malware-analysis, actor-profile, advisory, news, attribution, survey or methodology. Attribution, survey and methodology reports carry no victim or initial-access labels. If a report describes who was targeted, it is a campaign even when most of it analyses malware; malware-analysis is for reports whose victims are absent or only mentioned in passing (agreed 2026-10-07, prompt v3.1).


Stage 2 reads report text with a language model and records who was targeted and how the attackers got in. This document defines the labels, the rules for applying them, how results are scored, and how we build a test set of our own. Human labellers and the model prompt follow the same rules, so a disagreement between them points at a rule that needs fixing rather than a judgement call.

## 1. Why Not the Paper's Labels

The CCS '25 dataset labels 1,509 reports with victim countries, target sectors and attack vectors. We measured how consistent those labels are before building on them.

- **The sector list mixes three dimensions.** Government, Companies, NGOs, Individuals and Education are kinds of organization. Finance, Energy, Healthcare and Manufacturing are industries. Critical Infrastructure cuts across both. "Corporations and Businesses" appears on 73% of Manufacturing reports and more than half of Finance and Healthcare reports, so it works as a catch-all.
- **Common industries have no label.** Haiku produced 58 sector labels outside the paper's list on 200 reports, including telecommunications, transportation, aerospace and the defense industry.
- **The vector list mixes delivery, payload and post-compromise activity.** Spear Phishing (delivery) and Malicious Documents (payload) appear together on 59% of reports that carry either. Covert Channels and Meta Data Monitoring are not ways in. Phishing against Spear Phishing has no usable boundary: two prompts of the same model agreed on Phishing 18% of the time.
- **Countries look over-inclusive.** Reports average 3.9 victim countries, which suggests countries mentioned anywhere in a report were counted.
- **Model F1 against these labels stalls near 0.7.** Two prompts agreed with each other at about the same level as each agreed with the labels (0.70 to 0.80). The ceiling is the labels, not the models.

## 2. Principles

1. **Use published standards.** Initial access uses MITRE ATT&CK; sectors use the STIX 2.1 industry vocabulary. Both have definitions anyone can check, and both connect to other data (the site already shows ATT&CK techniques, and STIX allows a later export).
2. **One dimension per field.** Who was targeted, what industry they belong to and how the attackers got in are separate fields.
3. **Label the activity the report documents.** A background paragraph that recaps an actor's earlier campaigns is not the subject of this report and is not labelled.
4. **Stated or assessed, never guessed.** A label needs the report to state it or to give its own assessment ("likely delivered by spearphishing"). Speculation ("could be", "it is possible that") is not enough.
5. **An empty field is a valid answer.** Many reports do not say who was targeted or how the attackers got in.
6. **Closed lists only.** Every value comes from the lists below. Nothing else is stored, and no report text is stored.

## 3. Fields

### 3.1 Victim Countries

The countries where the targeted or compromised people and organizations are located.

Format: country names from the pipeline's list (`aptx/build/countries.py`), stored as ISO 3166-1 alpha-2 codes. The model is given names rather than codes, because codes invite errors such as `UK` for `GB`. There is no cap on the number of countries.

Include:
- Countries of named or described victims, including attempted targets in a stated campaign.
- A country the report names as a target of the campaign, even when no compromise is confirmed.

Exclude:
- The attacker's country or claimed origin.
- Countries that host infrastructure (C2 servers, staging sites).
- The country of the vendor that wrote the report.
- Countries of sample uploads or telemetry hits that the report does not present as victims.
- Countries that appear only in lure content, unless the report says victims were there.
- Regions ("Europe", "the Middle East"). Do not expand a region into countries.
- Countries from background sections about earlier campaigns.

### 3.2 Target Sectors

The industries of the targeted organizations, from the STIX 2.1 `industry-sector-ov` vocabulary (OASIS STIX 2.1, section 10.11).

| Value | Use for |
|---|---|
| `agriculture` | Farming, food production |
| `aerospace` | Aircraft and space manufacturing and research |
| `automotive` | Vehicle makers and suppliers |
| `chemical` | Chemical producers |
| `commercial` | Businesses that fit no more specific value; use only when the report gives no industry |
| `communications` | Media, news, publishing, broadcasting |
| `construction` | Construction and engineering firms |
| `defense` | Military, armed forces and the defense industrial base |
| `education` | Universities, schools, research institutes, think tanks attached to universities |
| `energy` | Oil, gas, power generation |
| `entertainment` | Gaming, film, music, gambling |
| `financial-services` | Banks, payments, cryptocurrency exchanges, investment firms |
| `government` | Government when the level is not stated |
| `government-national` | Ministries, national agencies, parliaments, embassies and diplomats |
| `government-regional` | State, province or regional government |
| `government-local` | City and municipal government |
| `government-public-services` | Public services run by government (tax, social security, postal) |
| `emergency-services` | Police, fire, emergency response |
| `healthcare` | Hospitals, clinics and health services |
| `hospitality-leisure` | Hotels, travel, tourism, restaurants |
| `infrastructure` | Critical infrastructure when no more specific value fits |
| `dams` | Dams and flood control |
| `nuclear` | Nuclear power and research |
| `water` | Water and wastewater |
| `insurance` | Insurers |
| `manufacturing` | Industrial and consumer manufacturing not covered above |
| `mining` | Mining and metals |
| `non-profit` | NGOs, charities, human-rights and advocacy groups, independent think tanks |
| `pharmaceuticals` | Drug makers and biotech |
| `retail` | Retail and e-commerce |
| `technology` | Software, IT services, managed service providers, cloud and hosting providers, hardware makers |
| `telecommunications` | Telecom and internet service providers |
| `transportation` | Airlines, shipping, logistics, rail, ports |
| `utilities` | Electricity and gas distribution, utilities in general |

Rules:
- Use the most specific value the report supports. Use `government-national` for a ministry, `government` only when the level is unclear.
- Several values are allowed. Do not add `commercial` next to a specific industry.
- A victim that is a person, not an organization, is recorded in 3.3, not here.

### 3.3 Individuals Targeted

`true` when the report says private individuals were targeted as people: activists, dissidents, journalists targeted personally, members of a diaspora, or the general public. `false` otherwise. Employees phished as a route into their employer do not count.

### 3.4 Initial Access

How the attackers first got in, as MITRE ATT&CK v19 Initial Access (TA0001) techniques.

| ID | Name | Use when the report says |
|---|---|---|
| `T1566.001` | Spearphishing Attachment | A malicious file was sent by email to chosen targets |
| `T1566.002` | Spearphishing Link | An email to chosen targets carried a link to a payload or credential page |
| `T1566.003` | Spearphishing via Service | The lure came through social media, messaging apps or job sites |
| `T1566.004` | Spearphishing Voice | Phone calls or voice messages were used to get access |
| `T1566` | Phishing | Phishing was used but the report does not say how it was delivered |
| `T1190` | Exploit Public-Facing Application | A vulnerability in an internet-facing system was exploited (VPN, mail server, web application, edge device) |
| `T1133` | External Remote Services | The attackers logged in through VPN, RDP, Citrix or similar remote access |
| `T1078` | Valid Accounts | Stolen, bought, guessed or default credentials were used to get in |
| `T1189` | Drive-by Compromise | Victims were infected by visiting a website, including watering holes and malvertising |
| `T1195` | Supply Chain Compromise | A software update, package, development tool or hardware was tampered with |
| `T1199` | Trusted Relationship | Access came through a supplier, IT provider or partner with existing access |
| `T1091` | Replication Through Removable Media | USB drives or other removable media |
| `T1200` | Hardware Additions | A device was physically connected to the victim network |
| `T1659` | Content Injection | Malicious content was injected into traffic on its way to the victim |
| `T1669` | Wi-Fi Networks | Access came through the victim's Wi-Fi |

Rules:
- A malicious document attached to a phishing email is `T1566.001`. The document is the payload, not a separate way in.
- A document exploit (for example a Word or PDF vulnerability) delivered by email is still `T1566.001`. `T1190` is only for internet-facing systems.
- `T1133` and `T1078` often appear together. Record both only when the report says both.
- Record more than one technique when the report describes different ways in for different victims.
- Do not record techniques from later stages (execution, persistence, command and control).

## 4. Scoring

- Precision, recall and F1, counted over all labels (micro-averaged), reported for each field.
- Sectors are also scored at the parent level, so `government-national` counts as a match for `government`.
- Initial access is also scored at the technique level, so `T1566.002` counts as a match for `T1566`.
- Scores are reported against two references: our test set (section 6), which is the headline figure, and the paper's labels mapped as in section 5, which is a secondary figure for comparison with earlier runs.

## 5. Mapping to the Paper's Labels

Model labels are mapped up to the paper's categories so the two can be compared. Labels with no paper equivalent are left out of that comparison.

| Paper category | Our values |
|---|---|
| Government and Defense Agencies | `government`, `government-*`, `emergency-services`, `defense` |
| Education and Research Institutions | `education` |
| Financial Institutions | `financial-services`, `insurance` |
| Energy and Utilities | `energy`, `utilities` |
| Critical Infrastructure | `infrastructure`, `dams`, `nuclear`, `water`, `telecommunications`, `transportation` |
| Media and Entertainment Companies | `communications`, `entertainment` |
| Non-Governmental Organizations (NGOs) and Nonprofits | `non-profit` |
| Healthcare | `healthcare`, `pharmaceuticals` |
| Manufacturing | `manufacturing`, `automotive`, `chemical`, `aerospace` |
| Individuals | Individuals Targeted is `true` |
| Corporations and Businesses | `commercial`, `retail`, `technology`, `hospitality-leisure`, `agriculture`, `construction`, `mining` |
| Cloud/IoT Services | not compared |

| Paper vector | Our family |
|---|---|
| Spear Phishing, Phishing, Malicious Documents, Social Engineering | `T1566` and its sub-techniques |
| Exploit Vulnerability | `T1190` |
| Watering Hole, Drive-by Download, Website Equipping | `T1189` |
| Credential Reuse | `T1078`, `T1133` |
| Removable Media | `T1091` |
| Covert Channels, Meta Data Monitoring | not compared (not initial access) |

Known loss: the paper's "Exploit Vulnerability" also covers document exploits delivered by email, which we record as `T1566.001`. The comparison scores those as misses for us.

## 6. Building Our Own Test Set

1. **Sample.** About 150 reports from the CCS '25 reports that are also in ORKL, stratified by year and by publisher, and kept apart from any prompt tuning.
2. **Pre-label.** Haiku and the local model each label every report under these guidelines.
3. **Adjudicate.** Where both models agree, the label is accepted after a spot check. Where they disagree, a human decides from the report and records the reason. A reason that recurs becomes a new rule in this document.
4. **Measure.** Report each model's precision, recall and F1 against the adjudicated set, and the agreement between the two models before adjudication.
5. **Freeze.** The test set is versioned. Prompt changes are tuned on other reports and scored on this set only.

A model alone never defines the reference answers, because the measurement would then grade itself.

## 7. Out of Scope for This Round

Network indicators, malware and tools, techniques described in prose, and incident narrative tags. They follow once these three fields hold up.

## References

- MITRE ATT&CK v19, Initial Access tactic TA0001: https://attack.mitre.org/tactics/TA0001/
- OASIS STIX 2.1, Industry Sector Vocabulary (section 10.11): https://docs.oasis-open.org/cti/stix/v2.1/os/stix-v2.1-os.html
- Yuldoshkhujaev et al., "A Decade-long Landscape of Advanced Persistent Threats", ACM CCS 2025 (arXiv 2509.07457).
