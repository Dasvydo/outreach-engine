"""Mail-provider detection by MX record.

The single highest-value enrichment available for this ICP. Gate G1 prefers
Microsoft 365 and Gmail carries a real cost (unverified-app consent screen, a
100-user lifetime cap), so knowing the provider *before* sending decides both
whether to contact a firm and which sequence it gets.

One DNS query per domain, no API key, no cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import dns.resolver
import dns.exception


class Provider(str, Enum):
    MICROSOFT = "microsoft"
    GOOGLE = "google"
    OTHER = "other"
    UNKNOWN = "unknown"  # NXDOMAIN, no MX, or lookup failed


# Substring -> provider. Checked against the lowercased MX target.
# Ordered most-specific first; the first hit wins.
_SIGNATURES: tuple[tuple[str, Provider], ...] = (
    ("outlook.com", Provider.MICROSOFT),          # *.mail.protection.outlook.com
    ("protection.outlook", Provider.MICROSOFT),
    ("microsoft.com", Provider.MICROSOFT),
    # Newer Exchange Online endpoint, e.g. redmark-dk.r-v1.mx.microsoft and
    # vbtm-nl.x-v1.mx.microsoft. Added 2026-09-03: both were sitting in the
    # campaign's own DK and NL candidate lists and were being classified OTHER,
    # so real Microsoft 365 firms were failing the hard gate. Found by probing
    # 84 real ICP domains, not by reading docs.
    (".mx.microsoft", Provider.MICROSOFT),
    ("google.com", Provider.GOOGLE),              # aspmx.l.google.com
    ("googlemail.com", Provider.GOOGLE),
    ("psmtp.com", Provider.GOOGLE),
)


@dataclass(frozen=True)
class MXResult:
    domain: str
    provider: Provider
    hosts: tuple[str, ...]

    @property
    def passes_g1(self) -> bool:
        """G1 prefers Microsoft. Not a hard disqualifier since 2026-08-31."""
        return self.provider is Provider.MICROSOFT


def classify(domain: str, timeout: float = 5.0) -> MXResult:
    """Resolve MX for `domain` and classify the mail provider.

    Never raises on DNS failure - an unresolvable domain is a data quality
    signal, not an error, and a crash mid-list would lose the whole run.
    """
    domain = domain.strip().lower().removeprefix("www.")
    if not domain:
        return MXResult(domain, Provider.UNKNOWN, ())

    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    resolver.timeout = timeout

    try:
        answers = resolver.resolve(domain, "MX")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
            dns.resolver.NoNameservers, dns.exception.Timeout):
        return MXResult(domain, Provider.UNKNOWN, ())
    except dns.exception.DNSException:
        return MXResult(domain, Provider.UNKNOWN, ())

    hosts = tuple(
        sorted(str(r.exchange).rstrip(".").lower() for r in answers)
    )
    if not hosts:
        return MXResult(domain, Provider.UNKNOWN, ())

    joined = " ".join(hosts)
    for needle, provider in _SIGNATURES:
        if needle in joined:
            return MXResult(domain, provider, hosts)

    return MXResult(domain, Provider.OTHER, hosts)
