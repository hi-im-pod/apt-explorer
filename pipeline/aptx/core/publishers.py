"""One name per publisher, and the publisher of a report the sources leave blank.

The sources spell one publisher several ways: "CrowdStrike", "Crowdstrike" and "crowdstrike",
or "Palo Alto" and "Palo Alto Networks". A name is matched on its letters and digits alone, and
a known name gives its canonical form. Any other name is kept as written.

A report with no publisher takes one from its address, but only when the host is a site the
publisher runs itself (HOSTS). A file host, a mirror or a blog platform names nobody, so it
is not listed and the publisher stays blank.
"""
import re
from urllib.parse import urlsplit

# Key (letters and digits, lower case) to the canonical name.
_CANONICAL = {
    "ahnlab": "AhnLab", "ahnlabinc": "AhnLab",
    "airbus": "Airbus", "alienvault": "AlienVault", "antiycert": "Antiy", "arbor": "Arbor Networks",
    "arbornetworks": "Arbor Networks", "baesystems": "BAE Systems", "bitdefender": "Bitdefender",
    "blackberry": "BlackBerry",
    "certua": "CERT-UA",
    "checkpoint": "Check Point",
    "cisa": "CISA", "uscert": "CISA", "cisco": "Cisco", "circl": "CIRCL", "citizenlab": "Citizen Lab",
    "ciscotalos": "Cisco Talos",
    "clearsky": "ClearSky",
    "crowdstrike": "CrowdStrike",
    "cyble": "Cyble", "cybereason": "Cybereason", "cylance": "Cylance",
    "deepinstinct": "Deep Instinct", "dellsecureworks": "Secureworks", "doctorwebltd": "Doctor Web",
    "drweb": "Doctor Web", "dragos": "Dragos",
    "eset": "ESET", "esetresearch": "ESET",
    "estsecurity": "ESTsecurity",
    "fidelis": "Fidelis", "fireeye": "FireEye", "forcepoint": "Forcepoint",
    "fsecure": "F-Secure", "fsecurecorporation": "F-Secure",
    "fortinet": "Fortinet",
    "foxit": "Fox-IT",
    "gdata": "G DATA",
    "groupib": "Group-IB", "idefense": "iDefense", "insiktgroup": "Recorded Future",
    "insiktgroupbyrecordedfuture": "Recorded Future", "intezer": "Intezer", "isightpartners": "iSight Partners",
    "jpcert": "JPCERT/CC", "lockheedmartin": "Lockheed Martin", "lookout": "Lookout",
    "intrusiontruth": "Intrusion Truth",
    "kaspersky": "Kaspersky", "kasperskylab": "Kaspersky",
    "malwarebytes": "Malwarebytes", "mcafee": "McAfee",
    "mandiant": "Mandiant",
    "microsoft": "Microsoft", "microsoftsecurity": "Microsoft",
    "nccgroup": "NCC Group", "ncsc": "NCSC", "netresec": "Netresec", "novetta": "Novetta",
    "nsfocus": "NSFOCUS",
    "paloalto": "Palo Alto Networks", "paloaltonetworks": "Palo Alto Networks",
    "pandalabs": "Panda Security", "proofpoint": "Proofpoint", "pwc": "PwC",
    "qianxin": "QiAnXin",
    "rapid7": "Rapid7", "recordedfuture": "Recorded Future", "rsa": "RSA",
    "root9b": "root9B",
    "secureworks": "Secureworks",
    "sentinelone": "SentinelOne", "sophos": "Sophos", "symantec": "Symantec",
    "stairwell": "Stairwell",
    "teamt5": "TeamT5",
    "telsy": "Telsy",
    "thedfirreport": "The DFIR Report",
    "threatconnect": "ThreatConnect", "threatpost": "Threatpost",
    "trendmicro": "Trend Micro", "trendmicroincorporated": "Trend Micro",
    "vincss": "VinCSS",
    "volexity": "Volexity", "zscaler": "Zscaler", "zscalerthreatlabz": "Zscaler",
}

# A host, or the domain it ends in, to the publisher that runs it.
HOSTS = {
    "ahnlab.com": "AhnLab", "anomali.com": "Anomali", "avast.com": "Avast", "avast.io": "Avast",
    "bitdefender.com": "Bitdefender", "blackberry.com": "BlackBerry", "cadosecurity.com": "Cado Security",
    "cert.gov.ua": "CERT-UA", "cert.pl": "CERT Polska", "cert.ssi.gouv.fr": "ANSSI",
    "checkpoint.com": "Check Point", "cisa.gov": "CISA", "us-cert.gov": "CISA", "citizenlab.ca": "Citizen Lab",
    "clearskysec.com": "ClearSky", "crowdstrike.com": "CrowdStrike", "cybereason.com": "Cybereason",
    "cyble.com": "Cyble", "cyfirma.com": "CYFIRMA", "cylance.com": "Cylance", "deepinstinct.com": "Deep Instinct",
    "dragos.com": "Dragos", "elastic.co": "Elastic", "esentire.com": "eSentire", "eset.com": "ESET",
    "welivesecurity.com": "ESET", "fireeye.com": "FireEye", "fortinet.com": "Fortinet",
    "gdatasoftware.com": "G DATA", "group-ib.com": "Group-IB", "huntress.com": "Huntress",
    "intel471.com": "Intel 471", "intezer.com": "Intezer", "jpcert.or.jp": "JPCERT/CC",
    "k7computing.com": "K7 Computing", "kaspersky.com": "Kaspersky", "securelist.com": "Kaspersky",
    "kroll.com": "Kroll", "malwarebytes.com": "Malwarebytes", "mandiant.com": "Mandiant",
    "microsoft.com": "Microsoft", "morphisec.com": "Morphisec", "nccgroup.com": "NCC Group",
    "netlab.360.com": "360 Netlab", "netskope.com": "Netskope", "paloaltonetworks.com": "Palo Alto Networks",
    "proofpoint.com": "Proofpoint", "ptsecurity.com": "Positive Technologies", "qianxin.com": "QiAnXin",
    "rapid7.com": "Rapid7", "recordedfuture.com": "Recorded Future", "redcanary.com": "Red Canary",
    "riskiq.com": "RiskIQ", "sekoia.io": "Sekoia", "sentinelone.com": "SentinelOne", "seqrite.com": "Seqrite",
    "securonix.com": "Securonix", "socradar.io": "SOCRadar", "splunk.com": "Splunk",
    "symantec-enterprise-blogs.security.com": "Symantec", "talosintelligence.com": "Cisco Talos",
    "threatfabric.com": "ThreatFabric", "trendmicro.com": "Trend Micro", "trustwave.com": "Trustwave",
    "volexity.com": "Volexity", "zscaler.com": "Zscaler",
    # News outlets publish their own articles.
    "arstechnica.com": "Ars Technica", "bankinfosecurity.com": "BankInfoSecurity",
    "bleepingcomputer.com": "BleepingComputer", "cyberscoop.com": "CyberScoop", "darkreading.com": "Dark Reading",
    "krebsonsecurity.com": "Krebs on Security", "securityaffairs.co": "Security Affairs",
    "securityweek.com": "SecurityWeek", "theregister.com": "The Register", "therecord.media": "The Record",
    "thehackernews.com": "The Hacker News", "threatpost.com": "Threatpost", "zdnet.com": "ZDNET",
    # Governments and research bodies.
    "cfr.org": "Council on Foreign Relations", "ic3.gov": "FBI IC3", "justice.gov": "U.S. Department of Justice",
    "virusbulletin.com": "Virus Bulletin",
}


def _key(name: str) -> str:
    return re.sub(r"[\W_]+", "", name.casefold())


def canonical_publisher(name: str | None) -> str | None:
    """The canonical spelling of a publisher's name, or the name tidied when it is not a known one."""
    if not isinstance(name, str) or not (text := " ".join(name.split())):
        return None
    return _CANONICAL.get(_key(text), text)


def publisher_for_url(url: str | None) -> str | None:
    """The publisher that runs the address's host, when HOSTS lists it."""
    host = (urlsplit(url or "").hostname or "").casefold()
    while host:
        if host in HOSTS:
            return HOSTS[host]
        host = host.partition(".")[2]
    return None


# Every name the tables above can give: the publishers this project knows.
KNOWN = frozenset(_CANONICAL.values()) | frozenset(HOSTS.values())

# A vendor's own blog or site named in a title, as the lab corpus files many papers:
# "The Naikon APT - Securelist", "ESET-LoJax", "...TrendLabs Security Intelligence Blog".
# Letters on neither side, so "_Securelist_2020" matches but a longer word does not.
_IN_TITLE = (
    (re.compile(r"(?<![a-z])securelist(?![a-z])", re.I), "Kaspersky"),
    (re.compile(r"(?<![a-z])welivesecurity(?![a-z])", re.I), "ESET"),
    (re.compile(r"^ESET(?![a-z])", re.I), "ESET"),
    (re.compile(r"(?<![a-z])trendlabs(?![a-z])", re.I), "Trend Micro"),
    (re.compile(r"(?<![a-z])talos intelligence(?![a-z])", re.I), "Cisco Talos"),
    (re.compile(r"(?<![a-z])the citizen lab(?![a-z])", re.I), "Citizen Lab"),
    (re.compile(r"[-_ ]clearsky$", re.I), "ClearSky"),
    (re.compile(r"(?<![a-z])unit ?42(?![0-9])", re.I), "Palo Alto Networks"),
)
_DOMAIN_PREFIX = re.compile(r"^((?:[a-z0-9-]+\.)+[a-z]{2,})-(?=[A-Za-z0-9])")


def known_publisher(name: str | None) -> str | None:
    """The canonical name when it is a publisher this project knows, else None.

    ORKL's authors field holds vendors, but also people's names and stray words such as "Appendix",
    so only a known name is kept from it.
    """
    name = canonical_publisher(name)
    return name if name in KNOWN else None


def publisher_in_title(title: str | None) -> str | None:
    """The publisher a title names as its own site or blog, or None."""
    title = " ".join((title or "").split())
    if m := _DOMAIN_PREFIX.match(title):
        if name := publisher_for_url("https://" + m.group(1)):
            return name
    return next((name for pattern, name in _IN_TITLE if pattern.search(title)), None)
