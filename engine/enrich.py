"""Mail-provider detection by MX record.

The single highest-value enrichment available for this ICP. The campaign now
targets Microsoft 365 mailboxes and nothing else, so this module decides whether
a firm is contacted at all - not merely how it is ranked. That raises the cost of
being wrong in both directions and is why the matching below is stricter than the
substring test it replaces.

One DNS query per domain, no API key, no cost.

WHAT CHANGED, AND WHY
---------------------
1. `GATEWAY` is now a provider state of its own. A firm can run Microsoft 365
   while its public MX points at a security gateway - Mimecast, Proofpoint,
   MessageLabs, Barracuda - because the gateway filters inbound mail before
   handing it to Exchange Online. Measured on 2026-09-14: `kpmg.nl` resolves to
   `mxa-00120b03.gslb.pphosted.com` (Proofpoint) and `bbc.co.uk` to
   `cluster1.eu.messagelabs.com`, and both are Microsoft shops underneath. Under
   the old code both classified as OTHER, and under an Outlook-only hard gate
   both would have been discarded. GATEWAY means "platform unknown, worth a
   look", not "not Microsoft", and the gate parks these rather than dropping
   them.

2. Matching is anchored per host instead of substring-matched across a joined
   string. The previous implementation lowercased every MX host, joined them with
   spaces and searched for substrings, which had two defects: a pattern could
   match across a host boundary, and `.mx.microsoft` was unanchored so any
   hostname merely containing it matched. Each host is now tested on its own with
   an exact-or-suffix rule.

3. Precedence follows MX preference. Mail is delivered to the lowest-preference
   record, so that host decides the verdict - not whichever pattern happened to
   appear first in a list. The one exception is a gateway in front: when the
   primary is a GATEWAY and some other record names a real platform, that
   platform is the answer, because a gateway is infrastructure in front of a
   mailbox rather than the mailbox itself.

4. UNKNOWN carries a reason. NXDOMAIN, "no MX record", a resolver timeout and a
   SERVFAIL are four different situations and only one of them is permanent. A
   transient timeout must not permanently discard a real prospect, so the reason
   is recorded and `MXResult.retryable` tells a batch runner what to come back
   to. See `engine/mxcache.py`.

A NOTE ON SPF, which is deliberately NOT used here
--------------------------------------------------
The obvious way to resolve a GATEWAY domain is to read its SPF record and look
for `include:spf.protection.outlook.com`. That is a sound signal and this module
does not use it, because TXT lookups do not work from the build container:
measured 2026-09-14 against the container resolver, 1.1.1.1 and 8.8.8.8, every
TXT query timed out while MX queries on the same domains succeeded. Code that
depends on a lookup that silently times out everywhere would classify every
gateway domain as "not Microsoft" and quietly delete them.

The tenant endpoint at login.microsoftonline.com is not used either, and that one
is not an environment problem - it simply does not mean what it appears to mean.
`anthropic.com` returns a valid tenant id while running Google Workspace, so the
endpoint proves an Entra ID presence and says nothing about where mail is
delivered. It was tested and rejected on 2026-09-14; please do not add it back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import dns.resolver
import dns.exception


class Provider(str, Enum):
    MICROSOFT = "microsoft"
    GOOGLE = "google"
    GATEWAY = "gateway"  # a security gateway fronts an unknown platform
    OTHER = "other"
    UNKNOWN = "unknown"  # NXDOMAIN, no MX, or the lookup failed


class Unresolved(str, Enum):
    """Why a domain came back UNKNOWN. Only NO_MX and NXDOMAIN are permanent."""

    NONE = ""
    NXDOMAIN = "nxdomain"          # the domain does not exist - permanent
    NO_MX = "no_mx"                # exists, publishes no MX - permanent
    TIMEOUT = "timeout"            # resolver gave up - retry
    SERVFAIL = "servfail"          # nameserver failed - retry
    EMPTY_DOMAIN = "empty_domain"  # nothing was passed in - caller's bug


# Exact host, or a suffix. Matched per host, never across a joined string.
# Ordered most-specific first within each provider; the first hit for a given
# host wins.
_MICROSOFT: tuple[str, ...] = (
    ".mail.protection.outlook.com",          # the classic tenant endpoint
    ".mail.protection.office365.us",         # GCC High and DoD
    ".mail.protection.partner.outlook.cn",   # 21Vianet, operated in China
    ".mx.microsoft",                         # newer Exchange Online, see 2026-09-03
    ".protection.outlook.com",
    ".outlook.com",
    ".microsoft.com",
)

_GOOGLE: tuple[str, ...] = (
    ".aspmx.l.google.com",
    ".l.google.com",
    "aspmx.l.google.com",
    "smtp.google.com",
    ".google.com",
    ".googlemail.com",
    ".psmtp.com",
)

# Security gateways. Mail passes through these on the way to a mailbox, so they
# tell you nothing about the platform behind them - which is the entire point of
# giving them their own state instead of lumping them into OTHER.
_GATEWAY: tuple[tuple[str, str], ...] = (
    (".mimecast.com", "Mimecast"),
    (".mimecast.co.za", "Mimecast"),
    (".mimecast-offshore.com", "Mimecast"),
    (".pphosted.com", "Proofpoint"),
    (".ppe-hosted.com", "Proofpoint"),
    (".messagelabs.com", "Broadcom/MessageLabs"),
    (".barracudanetworks.com", "Barracuda"),
    (".barracuda.com", "Barracuda"),
    (".iphmx.com", "Cisco IronPort"),
    (".cisco.com", "Cisco"),
    (".sophos.com", "Sophos"),
    (".hornetsecurity.com", "Hornetsecurity"),
    (".antispameurope.com", "Hornetsecurity"),
    (".libraesva.com", "Libraesva"),
    (".retarus.com", "Retarus"),
    (".tmes.trendmicro.com", "Trend Micro"),
    (".trendmicro.com", "Trend Micro"),
    (".spamtitan.com", "SpamTitan"),
    (".mailcontrol.com", "Forcepoint"),
    (".securence.com", "Securence"),
    (".fireeyecloud.com", "Trellix/FireEye"),
    (".emailfilteringservice.com", "generic filter"),
)


def _matches(host: str, pattern: str) -> bool:
    """Anchored: the host IS the pattern, or ends with it as a label boundary."""
    if pattern.startswith("."):
        return host.endswith(pattern) or host == pattern.lstrip(".")
    return host == pattern or host.endswith("." + pattern)


def classify_host(host: str) -> tuple[Provider, str]:
    """Classify ONE mail exchanger. Returns (provider, vendor-or-empty)."""
    host = host.strip().rstrip(".").lower()
    if not host:
        return Provider.UNKNOWN, ""
    for pattern in _MICROSOFT:
        if _matches(host, pattern):
            return Provider.MICROSOFT, "Microsoft 365"
    for pattern in _GOOGLE:
        if _matches(host, pattern):
            return Provider.GOOGLE, "Google Workspace"
    for pattern, vendor in _GATEWAY:
        if _matches(host, pattern):
            return Provider.GATEWAY, vendor
    return Provider.OTHER, ""


@dataclass(frozen=True)
class MXResult:
    domain: str
    provider: Provider
    hosts: tuple[str, ...]                 # ordered by MX preference, best first
    reason: Unresolved = Unresolved.NONE   # only meaningful when UNKNOWN
    vendor: str = ""                       # gateway vendor, when known
    per_host: tuple[tuple[str, str], ...] = field(default=())  # (host, provider)

    @property
    def passes_g1(self) -> bool:
        """G1 is satisfied by Microsoft and nothing else."""
        return self.provider is Provider.MICROSOFT

    @property
    def retryable(self) -> bool:
        """True when a second look could plausibly change the answer.

        A gateway is retryable in the sense that it deserves a second, richer
        look (SPF, or a human) rather than a second identical DNS query.
        """
        return self.reason in (Unresolved.TIMEOUT, Unresolved.SERVFAIL)

    @property
    def needs_review(self) -> bool:
        """A domain that must not be silently dropped by an Outlook-only gate."""
        return self.provider is Provider.GATEWAY or self.retryable


def _verdict(ordered_hosts: list[str]) -> tuple[Provider, str, tuple[tuple[str, str], ...]]:
    """Decide the domain's provider from its MX set, in preference order."""
    per_host = tuple((h, classify_host(h)[0].value) for h in ordered_hosts)
    classified = [classify_host(h) for h in ordered_hosts]
    if not classified:
        return Provider.UNKNOWN, "", per_host

    primary, vendor = classified[0]

    # A gateway is infrastructure in front of a mailbox, not the mailbox. If any
    # other record names a real platform, that platform is the answer - this is
    # the common "gateway primary, Exchange Online backup" shape.
    if primary is Provider.GATEWAY:
        for prov, _ in classified[1:]:
            if prov in (Provider.MICROSOFT, Provider.GOOGLE):
                return prov, "", per_host
        return Provider.GATEWAY, vendor, per_host

    return primary, vendor, per_host


def classify(domain: str, timeout: float = 5.0) -> MXResult:
    """Resolve MX for `domain` and classify the mail provider.

    Never raises on DNS failure - an unresolvable domain is a data quality
    signal, not an error, and a crash mid-list would lose the whole run. The
    failure mode is recorded in `.reason` so a batch runner can tell a permanent
    NXDOMAIN from a transient timeout worth retrying.
    """
    domain = domain.strip().lower().removeprefix("www.")
    if not domain:
        return MXResult(domain, Provider.UNKNOWN, (), Unresolved.EMPTY_DOMAIN)

    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    resolver.timeout = timeout

    try:
        answers = resolver.resolve(domain, "MX")
    except dns.resolver.NXDOMAIN:
        return MXResult(domain, Provider.UNKNOWN, (), Unresolved.NXDOMAIN)
    except dns.resolver.NoAnswer:
        return MXResult(domain, Provider.UNKNOWN, (), Unresolved.NO_MX)
    except dns.exception.Timeout:
        return MXResult(domain, Provider.UNKNOWN, (), Unresolved.TIMEOUT)
    except dns.resolver.NoNameservers:
        return MXResult(domain, Provider.UNKNOWN, (), Unresolved.SERVFAIL)
    except dns.exception.DNSException:
        return MXResult(domain, Provider.UNKNOWN, (), Unresolved.SERVFAIL)

    # Delivery follows the lowest preference value, so order by it rather than
    # alphabetically: the first host is the one that actually receives mail.
    ranked = sorted(
        ((int(r.preference), str(r.exchange).rstrip(".").lower()) for r in answers),
        key=lambda pair: (pair[0], pair[1]),
    )
    hosts = [h for _, h in ranked]
    if not hosts:
        return MXResult(domain, Provider.UNKNOWN, (), Unresolved.NO_MX)

    provider, vendor, per_host = _verdict(hosts)
    return MXResult(domain, provider, tuple(hosts), Unresolved.NONE, vendor, per_host)
