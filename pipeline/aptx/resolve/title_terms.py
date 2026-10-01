"""Terms that report titles repeat, and the context a name is written in.

Two things read the same titles. The guesser asks how a name sits in titles: is it followed
by "stealer", or by "threat actor"? The terms page asks which unknown names keep coming back
in titles, because a name that several publishers use may be a group nobody has catalogued.

Only the titles the site already publishes are read, as written by their publisher. Nothing
here reads an actor tag, and nothing is copied except a short title, which a page shows with a link.

A title is mostly ordinary words, so a candidate must have the shape of a name, not only be
capitalised: a Title Case headline capitalises everything. The shapes are the ones vendors use,
and each is a structural rule, not a list of names.
  id        a cluster ID such as UNC2452, Storm-0558, TA505 or APT-C-23.
  suffix    a name ending in an animal or weather word (Salt Typhoon, Fancy Bear), or starting with
            Water or Earth (Water Hydra).
  group     one or two name words followed by Group, Gang, Crew or APT.
  malware   a name word followed by a malware word (Zorklo Stealer).
  camel     one word with a capital inside it (ToddyCat, BlueNoroff).
  context   a name word written next to "threat actor" or "APT".
A word is not a name word when the titles themselves use it as an ordinary lower-case word, when
it is on NOT_NAMES, or when it is too short. NOT_NAMES was built by reading the most frequent
candidates over every published title (the offline evaluation in the build notes): each entry is
there because it ranked high and is a vendor, product, place or common word, not a name.
"""
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from aptx.build.countries import COUNTRIES
from aptx.resolve.names import norm
from aptx.resolve.similarity import _MALWARE_WORDS, _SUFFIX_WORDS

# The longest phrase, in words, that is counted in a title.
MAX_WORDS = 4

# A word the titles use in lower case this many times is an ordinary word, not a name.
ORDINARY_MIN = 4

# A name word needs at least this many letters.
MIN_NAME_LETTERS = 3

# Words after which a name is a group: "Lazarus Group", "Bahamut APT".
_GROUP_WORDS = frozenset({"group", "gang", "crew", "apt"})
_ANIMAL_WORDS = frozenset({
    "panda", "bear", "kitten", "chollima", "spider", "jackal", "leopard", "tiger", "buffalo", "wolf",
    "ocelot", "elephant", "typhoon", "blizzard", "sandstorm", "sleet", "tempest", "hail", "cyclone",
    "libra", "taurus", "scorpius", "ursa", "serpens", "lynx", "mantis", "hawk", "viper", "falcon",
    "werewolf", "dragon", "cobra", "scorpion", "tarantula", "gorilla"})
_PREFIX_NAMES = frozenset({"water", "earth"})
_MALWARE_SHAPE_WORDS = frozenset({
    "stealer", "infostealer", "loader", "rat", "ransomware", "botnet", "trojan", "backdoor", "banker",
    "dropper", "rootkit", "keylogger", "miner", "spyware", "wiper"})

# Words after, or before, a name that say it is an actor. Words after a name that say it is malware.
ACTOR_AFTER = frozenset({"actor", "actors", "apt", "group", "gang", "hackers", "crew"})
ACTOR_BEFORE = frozenset({"actor", "actors"})
MALWARE_AFTER = frozenset(_MALWARE_WORDS) | _MALWARE_SHAPE_WORDS | frozenset(w + "s" for w in _MALWARE_WORDS)
_ACTOR_PHRASE = frozenset({"actor", "actors", "group", "groups"})

# The suffix words a name carries in the guesser, so a name ending in one is not counted twice.
_ID_PREFIXES = frozenset({"unc", "uat", "ta", "dev", "storm", "tag", "fin", "apt", "temp", "uta", "unk", "uac"})
_ID_JOINED = re.compile(r"(unc|uat|ta|dev|tag|fin|apt|temp|uta|unk|uac|storm)(\d{1,5})")
_DIGITS = re.compile(r"\d{2,5}")
_CAMEL = re.compile(r"[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*")
_NON_WORD = re.compile(r"[^\w]+")

# Not names, though they are capitalised: vendors, platforms, products, places, and
# the months and days that a headline carries.
NOT_NAMES: frozenset[str] = frozenset(
    {name.casefold() for name in COUNTRIES.values()} | {
        # nationalities and regions
        "american", "chinese", "russian", "iranian", "korean", "north", "south", "east", "west", "european",
        "african", "asian", "arab", "indian", "pakistani", "ukrainian", "israeli", "turkish", "vietnamese",
        "japanese", "taiwanese", "brazilian", "german", "french", "british", "english", "spanish", "italian",
        "middle", "europe", "asia", "africa", "america", "americas", "nato", "eastern", "western", "southern",
        "northern", "central", "latin", "emea", "apac", "kremlin", "moscow", "beijing", "tehran", "pyongyang",
        "washington", "london", "kyiv", "kiev", "gaza", "crimea", "donbas", "palestine", "palestinian",
        # months and days
        "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
        "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        # vendors and teams that publish
        "microsoft", "google", "cisco", "talos", "eset", "kaspersky", "symantec", "broadcom", "mandiant",
        "crowdstrike", "proofpoint", "sophos", "fortinet", "fortiguard", "checkpoint", "paloalto", "unit42",
        "trellix", "mcafee", "fireeye", "secureworks", "recorded", "groupib", "positive", "technologies",
        "threatlabz", "zscaler", "akamai", "cloudflare", "cybereason", "sentinelone", "sentinellabs", "elastic",
        "volexity", "huntress", "rapid7", "qualys", "tenable", "malwarebytes", "bitdefender", "avast", "avg",
        "ahnlab", "lookout", "zimperium", "netskope", "okta", "vmware", "citrix", "ivanti", "apple", "adobe",
        "oracle", "amazon", "aws", "meta", "facebook", "twitter", "linkedin", "github", "gitlab", "dropbox",
        "telegram", "discord", "whatsapp", "signal", "tiktok", "youtube", "cert", "certua", "cisa", "fbi", "nsa",
        "gchq", "ncsc", "europol", "interpol", "enisa", "mitre", "attck", "nist", "sans", "owasp", "virustotal",
        "hybrid", "analysis", "trendmicro", "trend", "micro", "welivesecurity", "securelist", "unit", "lab",
        "labs", "research", "intelligence", "threatintel", "kroll", "deloitte", "pwc", "kpmg", "accenture",
        "ibm", "xforce", "dell", "hp", "lenovo", "samsung", "huawei", "zte", "xiaomi", "tp", "link", "netgear",
        "dlink", "asus", "cloudsek", "cyble", "sekoia", "orange", "cyberdefense", "tehtris", "stairwell",
        "esentire", "arctic", "wolf", "blackberry", "cylance", "ntt", "nttdata", "fujitsu", "toshiba", "hitachi",
        "nec", "yoroi", "yarix", "minerva", "morphisec", "intezer", "joesandbox", "anyrun", "any", "run",
        # platforms and products
        "windows", "linux", "android", "ios", "macos", "ubuntu", "debian", "redhat", "chrome", "firefox", "edge",
        "safari", "outlook", "office", "exchange", "sharepoint", "teams", "azure", "entra", "onedrive", "defender",
        "powershell", "python", "java", "javascript", "node", "nodejs", "npm", "pypi", "docker", "kubernetes",
        "wordpress", "joomla", "drupal", "apache", "nginx", "tomcat", "struts", "log4j", "log4shell", "spring",
        "fortigate", "fortios", "fortinac", "pulse", "secure", "anyconnect", "globalprotect", "netscaler",
        "sonicwall", "barracuda", "zyxel", "mikrotik", "juniper", "veeam", "solarwinds", "kaseya", "connectwise",
        "screenconnect", "teamviewer", "anydesk", "atlassian", "confluence", "jira", "zimbra", "roundcube",
        "moveit", "goanywhere", "citrixbleed", "chatgpt", "openai", "copilot", "gemini", "claude", "llm", "ai",
        "cobalt", "strike", "metasploit", "mimikatz", "sliver", "brute", "ratel", "havoc", "bloodhound",
        "ghidra", "ida", "wireshark", "yara", "sigma", "sysmon", "splunk", "qradar", "sentinel", "crowdsec",
        "bitcoin", "ethereum", "monero", "binance", "coinbase", "paypal", "visa", "mastercard", "zoom", "slack",
        "skype", "steam", "roblox", "minecraft", "fortnite", "ukraine", "russia", "iran", "israel", "korea",
        # vendors, products and document words that the camel-case and context shapes picked up
        "clearsky", "trendlabs", "blogpalo", "threatconnect", "paloaltonetworks", "whitepaper", "powerpoint",
        "stopransomware", "ccleaner", "dprk", "hacktivist", "hacktivists", "golang", "onenote", "iis", "corp", "rising", "deploying", "cryptojacking", "databreaches", "reversinglabs", "ddos", "mac", "iot", "pos", "understanding", "tesla", "kingdom", "netsupport", "encyclopedia", "conduct", "compromising", "professional",
        "temp", "proxyshell", "proxylogon", "eternalblue", "blackhat", "defcon", "bluehat", "recordedfuture",
        # products, vendors and sites that a first look at real titles showed in the lists
        "autoit", "vbscript", "winrar", "msbuild", "docusign", "keepass", "putty", "spacex", "vmray", "riskiq",
        "cyberark", "safebreach", "spiderlabs", "gosecure", "domaintools", "krebsonsecurity", "wikileaks",
        "breachforums", "infosec", "threatthursday", "weblogic", "oauth", "lolbin", "lolbins", "activemq",
        "teamcity", "webdav", "watchguard", "handbrake", "autocad", "applescript", "applescripts", "blogspot",
        "draytek", "iobit", "tightvnc", "softether", "windbg", "dnspy", "confuserex", "vmprotect", "vscode",
        "captchas", "websockets", "smartscreen", "cyberchef", "applocker", "manageengine", "vincss", "govcert",
        "brighttalk", "crowdcasts", "cybersoc", "mycert", "clickonce", "eventlog", "packetlogic", "ndisproxy",
        # ordinary words that a headline capitalises
        "coordinated", "prolific", "goals", "comment", "favorite", "modem", "nevada", "philadelphia", "chaining",
        "opsec", "multiplatform", "treatment", "unleashes", "simps",
        # words a headline capitalises that no one would call a name
        "the", "new", "how", "what", "why", "inside", "behind", "report", "analysis", "update", "alert", "advisory",
        "bulletin", "weekly", "daily", "monthly", "annual", "quarterly", "year", "review", "summary", "overview",
        "introduction", "guide", "tips", "best", "top", "case", "study", "part", "series", "episode", "webinar",
        "podcast", "video", "blog", "news", "press", "release", "notice", "warning", "threat", "threats",
        "security", "cyber", "cybersecurity", "malware", "ransomware", "phishing", "vulnerability", "vulnerabilities",
        "exploit", "exploits", "attack", "attacks", "attackers", "campaign", "campaigns", "operation", "operations",
        "actor", "actors", "group", "groups", "gang", "gangs", "crew", "hackers", "hacker", "hacking", "state",
        "sponsored", "nation", "national", "global", "world", "international", "financial", "government", "military",
        "defense", "defence", "energy", "healthcare", "education", "telecom", "technology", "industrial", "critical",
        "infrastructure", "supply", "chain", "zero", "day", "remote", "code", "execution", "privilege", "escalation",
        "bypass", "injection", "overflow", "disclosure", "leak", "breach", "incident", "response", "forensics",
        "mobile", "cloud", "web", "network", "email", "data", "access", "control", "identity", "password",
        "credential", "credentials", "token", "tokens", "key", "keys", "file", "files", "image", "images",
        "package", "packages", "library", "libraries", "plugin", "plugins", "extension", "extensions", "app", "apps",
        "game", "games", "gaming", "site", "sites", "page", "pages", "server", "servers", "service", "services",
        "platform", "platforms", "system", "systems", "software", "hardware", "firmware", "device", "devices",
        "router", "routers", "camera", "cameras", "driver", "drivers", "kernel", "bootkit", "uefi", "bios",
        "tracking", "tracker", "dashboard", "tool", "tools", "toolkit", "framework", "kit", "kits", "service",
        "evolution", "rise", "fall", "return", "returns", "revisited", "again", "targets", "targeting", "targeted",
        "using", "uses", "used", "abusing", "abuses", "exploiting", "exploits", "delivers", "delivering",
        "spreading", "spreads", "hunting", "hunt", "detecting", "detection", "analyzing", "analysing", "unmasking",
        "unveiling", "uncovering", "exposing", "discovering", "dissecting", "deep", "dive", "technical",
        "breaking", "latest", "recent", "ongoing", "active", "massive", "major", "large", "scale", "global",
        "multi", "stage", "multistage", "advanced", "persistent", "threatactor", "unknown", "unnamed", "various",
        "mass", "wave", "waves", "surge", "spike", "trend", "trends", "landscape", "outlook", "forecast",
        "predictions", "lessons", "learned", "story", "stories", "chronicle", "timeline", "history", "anatomy",
        "life", "cycle", "lifecycle", "playbook", "handbook", "manual", "checklist", "framework", "model", "models",
    })

# Weather and animal names are suffix words, so "Typhoon" alone is not a name either.
_SUFFIX_ONLY = _ANIMAL_WORDS | _GROUP_WORDS | _MALWARE_SHAPE_WORDS | _PREFIX_NAMES | frozenset(_SUFFIX_WORDS)


@dataclass(frozen=True)
class Title:
    """A published report title: what the site shows, and how to find the report again."""
    id: str
    text: str
    published: str | None
    organisation: str | None
    url: str | None


@dataclass
class TitleStat:
    """How one name key sits in the titles: which titles carry it, and what the words around it say."""
    indices: list[int] = field(default_factory=list)
    malware_titles: int = 0
    actor_titles: int = 0

    @property
    def titles(self) -> int:
        return len(self.indices)


@dataclass
class Candidate:
    """A phrase that has the shape of a name, with the spellings and shapes it was found in."""
    key: str
    tokens: tuple[str, ...]
    spellings: Counter = field(default_factory=Counter)
    shapes: Counter = field(default_factory=Counter)

    @property
    def name(self) -> str:
        return max(self.spellings, key=lambda s: (self.spellings[s], s))


def _split(text: str) -> list[str]:
    return _NON_WORD.sub(" ", unicodedata.normalize("NFKC", text)).split()


def _key(tokens: Sequence[str]) -> str:
    """The key norm() gives the same words: joined, and without a trailing 'group' or 'team'."""
    parts = list(tokens)
    if len(parts) > 1 and parts[-1] in ("group", "team"):
        parts.pop()
    return "".join(parts)


def is_usable_title(text: str) -> bool:
    """Whether a title can be read: a title with a corrupted character may have lost the name's letters."""
    return bool(text) and "�" not in text and not text.startswith(("http://", "https://"))


class TitleIndex:
    """Every readable title, split into words once, and what can be asked of them."""

    def __init__(self, titles: Iterable[Title]):
        self.titles = [t for t in titles if is_usable_title(t.text)]
        self._raw = [_split(t.text) for t in self.titles]
        self._folded = [[w.casefold() for w in tokens] for tokens in self._raw]
        lower = Counter()
        for tokens in self._raw:
            for w in tokens:
                if w.islower():
                    lower[w] += 1
        self._lower = lower

    def ordinary(self, word: str) -> bool:
        """Whether the titles use this word as an ordinary lower-case word."""
        return self._lower[word.casefold()] >= ORDINARY_MIN

    def _name_word(self, raw: str, minimum: int = MIN_NAME_LETTERS) -> bool:
        folded = raw.casefold()
        return (len(raw) >= minimum and raw[0].isupper() and raw.isalnum() and not raw.isdigit()
                and sum(c.isalpha() for c in raw) >= minimum and folded not in NOT_NAMES
                and folded not in _SUFFIX_ONLY and not self.ordinary(raw))

    # What the words around a name say

    def stats(self, phrases: Iterable[str]) -> dict[str, TitleStat]:
        """For each phrase, keyed by norm(): the titles that carry it as whole words, and what is around it.

        A phrase of more than MAX_WORDS words is not counted. A title is counted once for a key, and it
        counts for the malware or actor context when any place the key appears has that context.
        """
        wanted: dict[str, int] = {}
        starts: set[str] = set()
        for phrase in phrases:
            tokens = [w.casefold() for w in _split(phrase)]
            key = _key(tokens)
            if key and 0 < len(tokens) <= MAX_WORDS:
                wanted.setdefault(key, len(tokens))
                starts.add(tokens[0])
        out = {key: TitleStat() for key in wanted}
        for index, folded in enumerate(self._folded):
            seen: dict[str, tuple[bool, bool]] = {}
            size = len(folded)
            for i, word in enumerate(folded):
                if word not in starts:
                    continue
                for n in range(1, min(MAX_WORDS, size - i) + 1):
                    key = _key(folded[i:i + n])
                    if key not in wanted:
                        continue
                    after = folded[i + n] if i + n < size else ""
                    after2 = folded[i + n + 1] if i + n + 1 < size else ""
                    before = folded[i - 1] if i else ""
                    malware = after in MALWARE_AFTER or before == "malware"
                    actor = (after in ACTOR_AFTER or (after == "threat" and after2 in _ACTOR_PHRASE)
                             or before in ACTOR_BEFORE)
                    was = seen.get(key, (False, False))
                    seen[key] = (was[0] or malware, was[1] or actor)
            for key, (malware, actor) in seen.items():
                stat = out[key]
                stat.indices.append(index)
                stat.malware_titles += malware
                stat.actor_titles += actor
        return out

    # Names that titles repeat

    def candidates(self, is_known: Callable[[str], bool], minimum_titles: int = 3) -> dict[str, Candidate]:
        """Phrases with the shape of a name that no source lists, found in at least `minimum_titles` titles.

        `is_known` says whether a source already lists the phrase as an actor or as software.
        """
        found: dict[str, Candidate] = {}
        titles_by_key: dict[str, set[int]] = defaultdict(set)
        for index, raw in enumerate(self._raw):
            for tokens, shape, spelling in self._shapes(raw):
                folded = tuple(w.casefold() for w in tokens)
                key = _key(folded)
                if not key:
                    continue
                cand = found.setdefault(key, Candidate(key, folded))
                cand.spellings[spelling] += 1
                cand.shapes[shape] += 1
                titles_by_key[key].add(index)
        kept = {k: c for k, c in found.items() if len(titles_by_key[k]) >= minimum_titles}
        return {k: c for k, c in kept.items()
                if not is_known(c.name) and not is_known(" ".join(c.tokens)) and not is_known(c.tokens[-1])}

    def _with_shape(self, raw: list[str], covered: set[int], i: int, shape: str, emit):
        """A name followed by a shape word. A second name word before it is part of the name."""
        start = i - 1 if i > 0 and (i - 1) not in covered and self._name_word(raw[i - 1]) else i
        return emit(start, i + 2, shape, core_end=i + 1)

    def _shapes(self, raw: list[str]) -> Iterable[tuple[list[str], str, str]]:
        n = len(raw)
        folded = [w.casefold() for w in raw]
        covered: set[int] = set()

        def emit(start: int, end: int, shape: str, spelling: str | None = None, core_end: int | None = None):
            covered.update(range(start, end))
            core = raw[start:core_end or end]
            return core, shape, spelling or " ".join(core)

        for i in range(n):
            joined = _ID_JOINED.fullmatch(folded[i])
            if joined and (len(joined.group(2)) >= 2 or joined.group(1) == "fin"):
                prefix, digits = joined.groups()
                yield emit(i, i + 1, "id", _canonical_id(prefix, digits))
                continue
            if folded[i] in _ID_PREFIXES and i + 1 < n and _DIGITS.fullmatch(folded[i + 1]):
                yield emit(i, i + 2, "id", _canonical_id(folded[i], folded[i + 1]))
                continue
            if folded[i] == "apt" and i + 2 < n and len(folded[i + 1]) == 1 and folded[i + 1].isalpha() \
                    and _DIGITS.fullmatch(folded[i + 2]):
                yield emit(i, i + 3, "id", f"APT-{folded[i + 1].upper()}-{folded[i + 2]}")
                continue
            if folded[i] == "cl" and i + 2 < n and len(folded[i + 1]) == 3 and folded[i + 1].isalpha() \
                    and _DIGITS.fullmatch(folded[i + 2]):
                yield emit(i, i + 3, "id", f"CL-{folded[i + 1].upper()}-{folded[i + 2]}")
                continue
        for i in range(n):
            if i in covered:
                continue
            word = raw[i]
            nxt = folded[i + 1] if i + 1 < n else ""
            prev = folded[i - 1] if i else ""
            if folded[i] in _PREFIX_NAMES and i + 1 < n and self._name_word(raw[i + 1], 4):
                yield emit(i, i + 2, "suffix")
                continue
            if self._name_word(word) and nxt in _ANIMAL_WORDS - _GROUP_WORDS:
                yield emit(i, i + 2, "suffix")
                continue
            if nxt in _GROUP_WORDS and self._name_word(word):
                yield self._with_shape(raw, covered, i, "group", emit)
                continue
            if nxt in _MALWARE_SHAPE_WORDS and self._name_word(word):
                yield self._with_shape(raw, covered, i, "malware", emit)
                continue
            if _CAMEL.fullmatch(word) and any(c.isupper() for c in word[1:]) and len(word) >= 5 \
                    and word.isalnum() and word.casefold() not in NOT_NAMES and not self.ordinary(word):
                yield emit(i, i + 1, "camel")
                continue
            actor_next = nxt in ACTOR_AFTER or (nxt == "threat" and i + 2 < n and folded[i + 2] in _ACTOR_PHRASE)
            if (actor_next or prev in ACTOR_BEFORE) and self._name_word(word, 4):
                previous_is_name = i > 0 and self._name_word(raw[i - 1])
                if not previous_is_name:
                    yield emit(i, i + 1, "context")


def _canonical_id(prefix: str, digits: str) -> str:
    prefix = prefix.casefold()
    if prefix in ("storm", "dev", "uat", "tag", "temp", "unk", "uac"):
        return f"{prefix.capitalize() if prefix == 'storm' else prefix.upper()}-{digits}"
    return f"{prefix.upper()}{digits}"
