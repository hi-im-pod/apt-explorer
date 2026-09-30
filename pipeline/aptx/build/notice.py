"""The credits every copy of data/ must carry, and the text of data/NOTICE.md.

CC BY-NC-SA and MITRE's licence both require the credits to travel with the
data. data/NOTICE.md is the copy that travels with the files, so the pipeline
writes it on every build instead of leaving it as a file a person must
remember to keep in step with SOURCES.md. The wording below is SOURCES.md's
attribution text character for character, and a test fails if the two drift.

sources.json, trends.json's source health and the About page all read the same
SOURCE_INFO, so a source has one licence name, one link and one credit
wherever the site shows it.
"""
import re
from dataclasses import dataclass

# The order sources.json lists them in, and the order NOTICE.md credits them
# in after MITRE, which has its own section.
SOURCE_ORDER = ("attack", "misp", "etda", "malpedia", "orkl", "kev", "dfir", "paper")

_YEAR = re.compile(r"[0-9]{4}")


def require_year(copyright_year: str | None) -> str:
    """The copyright year, or a ValueError when there is none to use.

    MITRE's licence asks for its copyright designation in every copy. The year
    comes from the licence file the pipeline fetched, and a build that cannot
    read it must stop, because writing last year's or a guessed year would put
    a wrong statement into a legal notice.
    """
    if not isinstance(copyright_year, str) or not _YEAR.fullmatch(copyright_year):
        raise ValueError(
            f"cannot write the MITRE copyright designation: no four-digit year was read from "
            f"ATT&CK's licence file (got {copyright_year!r}). Read the licence again and fix "
            f"the connector before building.")
    return copyright_year


@dataclass(frozen=True)
class SourceInfo:
    key: str
    title: str
    licence: str
    licence_url: str
    # The attribution as paragraphs. "{year}" stands for MITRE's copyright year
    # and appears only in ATT&CK's first paragraph.
    _paragraphs: tuple[str, ...]
    # A sentence NOTICE.md adds under the credit that sources.json does not
    # carry, such as KEV's condition on the CISA logo.
    extra: str | None = None

    def paragraphs(self, copyright_year: str | None = None) -> tuple[str, ...]:
        if any("{year}" in p for p in self._paragraphs):
            year = require_year(copyright_year)
            return tuple(p.replace("{year}", year) for p in self._paragraphs)
        return self._paragraphs


SOURCE_INFO: dict[str, SourceInfo] = {i.key: i for i in (
    SourceInfo(
        key="attack",
        title="MITRE ATT&CK",
        licence="MITRE ATT&CK® Terms of Use",
        licence_url="https://attack.mitre.org/resources/legal-and-branding/terms-of-use/",
        _paragraphs=(
            "© {year} The MITRE Corporation. This work is reproduced and distributed with the permission of "
            "The MITRE Corporation.",
            "The MITRE Corporation (MITRE) hereby grants you a non-exclusive, royalty-free license to use "
            "ATT&CK® for research, development, and commercial purposes. Any copy you make for such purposes "
            "is authorized provided that you reproduce MITRE's copyright designation and this license in any "
            "such copy.",
            "MITRE ATT&CK® and ATT&CK® are registered trademarks of The MITRE Corporation.",
        )),
    SourceInfo(
        key="misp",
        title="MISP galaxy threat-actor cluster",
        licence="CC0 1.0",
        licence_url="https://raw.githubusercontent.com/MISP/misp-galaxy/main/LICENSE.md",
        _paragraphs=(
            "Threat actor data from the MISP galaxy threat-actor cluster (MISP Project; authors Alexandre "
            "Dulaunoy, Florian Roth, Thomas Schreck, Timo Steffens and others), "
            "https://github.com/MISP/misp-galaxy, used under CC0 1.0.",
        )),
    SourceInfo(
        key="etda",
        title="ETDA Threat Group Cards",
        licence="CC BY-NC-SA 4.0",
        licence_url="https://creativecommons.org/licenses/by-nc-sa/4.0/",
        _paragraphs=(
            "Threat Group Cards: A Threat Actor Encyclopedia. Copyright © Electronic Transactions Development "
            "Agency, 2019-2026. https://apt.etda.or.th/. Licensed under CC BY-NC-SA 4.0, "
            "https://creativecommons.org/licenses/by-nc-sa/4.0/. Provided by ETDA on an 'As Is' basis with no "
            "warranty. Modified: names and values were normalized and merged with other sources by "
            "apt-explorer.",
        )),
    SourceInfo(
        key="malpedia",
        title="Malpedia",
        licence="CC BY-NC-SA 3.0",
        licence_url="https://creativecommons.org/licenses/by-nc-sa/3.0/",
        _paragraphs=(
            "Malpedia, a free service offered by Fraunhofer FKIE. https://malpedia.caad.fkie.fraunhofer.de/. "
            "Licensed under CC BY-NC-SA 3.0, https://creativecommons.org/licenses/by-nc-sa/3.0/. Modified: "
            "actor, family and library data were normalized and merged with other sources by apt-explorer.",
            "Plohmann, D., Clauss, M., Enders, S., Padilla, E. Malpedia: A Collaborative Effort to Inventorize "
            "the Malware Landscape. The Journal on Cybercrime & Digital Investigations, [S.l.], v. 3, n. 1, "
            "apr. 2018.",
        )),
    SourceInfo(
        key="orkl",
        title="ORKL",
        licence="No licence stated",
        licence_url="https://orkl.eu/about",
        _paragraphs=(
            "Report metadata from ORKL, the community cyber threat intelligence library, https://orkl.eu.",
        )),
    SourceInfo(
        key="kev",
        title="CISA Known Exploited Vulnerabilities Catalog",
        licence="CC0 1.0",
        licence_url="https://www.cisa.gov/sites/default/files/licenses/kev/license.txt",
        _paragraphs=(
            "CISA Known Exploited Vulnerabilities Catalog, "
            "https://www.cisa.gov/known-exploited-vulnerabilities-catalog, CC0 1.0.",
        ),
        extra="Use of the information does not authorize you to use the CISA Logo or DHS Seal, nor should such "
              "use be interpreted as an endorsement by CISA or DHS."),
    SourceInfo(
        key="dfir",
        title="The DFIR Report",
        licence="All rights reserved",
        licence_url="https://thedfirreport.com/",
        _paragraphs=(
            "Report titles and links from The DFIR Report, https://thedfirreport.com/. © The DFIR Report. All "
            "rights reserved; report content is not reproduced here.",
        )),
    SourceInfo(
        key="paper",
        title="Yuldoshkhujaev et al., CCS '25 dataset, Zenodo 16869733",
        licence="CC BY 4.0",
        licence_url="https://creativecommons.org/licenses/by/4.0/",
        _paragraphs=(
            "Data from Yuldoshkhujaev, S., Jeon, M., Kim, D., Nikiforakis, N., Koo, H. A Decade-long Landscape "
            "of Advanced Persistent Threats: Longitudinal Analysis and Global Trends. Proceedings of the 2025 "
            "ACM SIGSAC Conference on Computer and Communications Security (CCS '25). Dataset: "
            "https://doi.org/10.5281/zenodo.16869733, licensed under CC BY 4.0, "
            "https://creativecommons.org/licenses/by/4.0/. Modified: rows were parsed, split and filtered by "
            "apt-explorer.",
        )),
)}
assert tuple(SOURCE_INFO) == SOURCE_ORDER


def source_attribution(key: str, copyright_year: str | None) -> str:
    """The credit for one source on a single line, as sources.json carries it."""
    return " ".join(SOURCE_INFO[key].paragraphs(copyright_year))


_INTRO = """\
# Data licence and attribution

The files in this directory are offered under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International licence (CC BY-NC-SA 4.0): https://creativecommons.org/licenses/by-nc-sa/4.0/

They carry this licence because they adapt two share-alike sources. Values from ETDA's Threat Group Cards (CC BY-NC-SA 4.0) and from Malpedia (CC BY-NC-SA 3.0) are normalized and merged with the other sources, and both licences require adapted material to be shared under the same licence elements. Anyone who reuses these files receives the same NonCommercial and ShareAlike terms and must credit the sources below.

No additional terms or conditions apply to these files. The licence of the apt-explorer code does not apply to them.

Related work: APT Map (https://lngt-apt-study-map.vercel.app/) is a separate interactive map built from the same paper dataset that appears below as the `paper` source.
"""

_MITRE_LEAD_IN = ("Values from MITRE ATT&CK® stay under MITRE's licence, which requires its copyright "
                  "designation and licence in every copy:")

_OTHER_SOURCES_LEAD_IN = "Each source's attribution, as SOURCES.md in the apt-explorer repository records it."


def render_notice(copyright_year: str | None) -> str:
    """The text of data/NOTICE.md.

    Every source is credited whatever its publish value is in this build. The
    notice describes the files' licence, and ETDA and Malpedia stay merge
    evidence even in a build that hides their values. Raises ValueError when
    copyright_year is missing or malformed; see require_year.
    """
    year = require_year(copyright_year)
    mitre = SOURCE_INFO["attack"]
    blocks = [_INTRO.rstrip("\n"), "## MITRE ATT&CK", _MITRE_LEAD_IN, *mitre.paragraphs(year),
              "## Other sources", _OTHER_SOURCES_LEAD_IN]
    for key in SOURCE_ORDER[1:]:
        info = SOURCE_INFO[key]
        blocks.append(f"### {info.title} (`{key}`)")
        blocks.extend(info.paragraphs(year))
        if info.extra:
            blocks.append(f"The KEV licence also states: \"{info.extra}\"")
    return "\n\n".join(blocks) + "\n"
