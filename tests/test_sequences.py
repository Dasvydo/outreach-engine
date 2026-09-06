"""Every sequence file exists, in the right language, with correct UTMs.

Copy quality is a deliverable, so these are checks on the copy itself, not just
on the files being present.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SEQ = ROOT / "sequences"

EXPECTED = {
    "linkedin/en.md": ("global", "en"),
    "linkedin/da.md": ("dk", "da"),
    "linkedin/lt.md": ("lt", "lt"),
    "email/en.md": ("global", "en"),
    "phone/da.md": ("dk", "da"),
    "phone/en.md": ("global", "en"),
    "phone/lt.md": ("lt", "lt"),
}

# The template exactly as the campaign spec writes it. Every sequence carries it.
SPEC_UTM = ("?utm_source=linkedin&utm_medium=dm&utm_campaign=teams_q4"
            "&utm_content={market}_{step}")

ALL_FILES = sorted(EXPECTED)


@pytest.mark.parametrize("relative", ALL_FILES)
def test_the_file_exists(relative):
    assert (SEQ / relative).exists(), f"missing sequence file {relative}"


def test_there_are_no_extra_or_missing_sequence_files():
    on_disk = sorted(str(p.relative_to(SEQ)) for p in SEQ.rglob("*.md"))
    assert on_disk == ALL_FILES


@pytest.mark.parametrize("relative", ALL_FILES)
def test_no_em_dashes(relative):
    """Campaign copy rule. An en dash used as an em dash is out too."""
    body = (SEQ / relative).read_text(encoding="utf-8")
    assert "—" not in body, f"em dash in {relative}"
    assert " – " not in body, f"en dash used as an em dash in {relative}"


@pytest.mark.parametrize("relative", ALL_FILES)
def test_carries_the_spec_utm_template_verbatim(relative):
    body = (SEQ / relative).read_text(encoding="utf-8")
    assert SPEC_UTM in body, f"{relative} does not carry the spec's UTM template"


@pytest.mark.parametrize("relative", ALL_FILES)
def test_filled_utms_use_this_files_market(relative):
    market, _ = EXPECTED[relative]
    body = (SEQ / relative).read_text(encoding="utf-8")
    filled = re.findall(r"utm_content=([a-z]+)_(\d)", body)
    concrete = [(m, s) for m, s in filled]
    assert concrete, f"{relative} has no filled utm_content"
    for found_market, step in concrete:
        assert found_market == market, \
            f"{relative} carries utm_content={found_market}_{step}, expected {market}"
        assert step in "1234"


@pytest.mark.parametrize("relative", ALL_FILES)
def test_every_link_points_at_the_campaign_landing_page(relative):
    body = (SEQ / relative).read_text(encoding="utf-8")
    for url in re.findall(r"https?://\S+", body):
        if "utm_" in url:
            assert url.startswith("https://teams.doviloop.dev/"), url
            assert "utm_campaign=teams_q4" in url, url


@pytest.mark.parametrize("relative", [f for f in ALL_FILES if f.endswith(("da.md", "lt.md"))])
def test_danish_and_lithuanian_are_headed_needs_native_check(relative):
    first = (SEQ / relative).read_text(encoding="utf-8").splitlines()[0]
    assert first.strip() == "# NEEDS NATIVE CHECK", \
        f"{relative} must open with the native-check header, got {first!r}"


def test_english_files_are_not_marked_needs_native_check():
    for relative in ALL_FILES:
        if relative.endswith("en.md"):
            first = (SEQ / relative).read_text(encoding="utf-8").splitlines()[0]
            assert "NEEDS NATIVE CHECK" not in first


def test_lithuanian_uses_the_formal_register():
    """Formal Jūs, not the familiar tu. Checked on the actual message text."""
    for relative in ("linkedin/lt.md", "phone/lt.md"):
        body = (SEQ / relative).read_text(encoding="utf-8")
        assert "Jūs" in body or "Jūsų" in body, f"{relative} is missing the formal register"
        # The familiar forms, as standalone words.
        for familiar in (" tu ", " tavo ", " tave "):
            assert familiar not in body.lower(), \
                f"{relative} slipped into the familiar register at {familiar!r}"


def test_the_connect_step_stays_under_the_linkedin_limit():
    hooks = yaml.safe_load((ROOT / "config" / "hooks.yaml").read_text(encoding="utf-8"))
    for segment, by_locale in hooks["segments"].items():
        for locale in ("en", "da", "lt"):
            note = " ".join(by_locale[locale]["connect"].split())
            rendered = note.format(first_name="Charlotte", company="Example Firm")
            assert len(rendered) < 300, f"{segment}/{locale} connect note is {len(rendered)}"


def test_step_two_carries_no_link():
    """The spec is explicit: day 2 is one line and one question, no link."""
    for relative in ("linkedin/en.md", "linkedin/da.md", "linkedin/lt.md"):
        body = (SEQ / relative).read_text(encoding="utf-8")
        # Step 2 runs from its heading to the next one.
        chunks = re.split(r"\n## ", body)
        step_two = [c for c in chunks if c.startswith(("Step 2", "Trin 2", "2 žingsnis"))]
        assert step_two, f"{relative} has no step 2 heading"
        assert "teams.doviloop.dev" not in step_two[0], \
            f"{relative} step 2 contains a link and should not"


def test_hooks_cover_every_segment_and_locale():
    hooks = yaml.safe_load((ROOT / "config" / "hooks.yaml").read_text(encoding="utf-8"))
    slots = ("connect", "pain", "question", "link_line", "reel_line",
             "email_subject", "email_opener", "phone_opener")
    for segment in ("accounting", "insurance", "housing_admin"):
        for locale in ("en", "da", "lt"):
            for slot in slots:
                value = hooks["segments"][segment][locale][slot]
                assert value and value.strip(), f"{segment}/{locale}/{slot} is empty"
                assert "—" not in value, f"em dash in {segment}/{locale}/{slot}"


def test_no_unfilled_placeholders_are_left_in_the_copy():
    """No {{placeholder}} sprinkled over nothing. Instantly variables are named."""
    allowed = {"{{firstName}}", "{{companyName}}", "{{segmentOpener}}"}
    for relative in ALL_FILES:
        body = (SEQ / relative).read_text(encoding="utf-8")
        for found in set(re.findall(r"\{\{[^}]+\}\}", body)):
            assert found in allowed, f"{relative} carries an undocumented {found}"


def _message_text(relative: str) -> str:
    """Only the lines that actually get sent.

    Sequence files are half copy and half instructions to whoever runs them. The
    copy is the blockquoted part, so checks on what a prospect reads look only
    there. The instructions are allowed to say "do not invent testimonials"; the
    message is not allowed to contain one.
    """
    body = (SEQ / relative).read_text(encoding="utf-8")
    return "\n".join(line.lstrip("> ").rstrip()
                     for line in body.splitlines() if line.startswith(">")).lower()


def test_no_invented_social_proof():
    """No testimonials and no named pilots exist. The copy must not imply any."""
    banned = ("testimonial", "our client said", "case study", "customers like",
              "trusted by", "join hundreds", "one of our customers")
    for relative in ALL_FILES:
        text = _message_text(relative)
        assert text, f"{relative} has no quoted message copy at all"
        for phrase in banned:
            assert phrase not in text, f"{relative} implies social proof: {phrase!r}"


def test_no_ai_flavoured_phrasing_in_the_copy():
    """Campaign voice rule. Checked on the message text, not the notes."""
    banned = ("unlock", "supercharge", "in today's fast-paced", "game changer",
              "game-changer", "seamlessly", "leverage", "revolutionize",
              "revolutionise", "cutting-edge", "delve", "elevate your")
    for relative in ALL_FILES:
        text = _message_text(relative)
        for phrase in banned:
            assert phrase not in text, f"{relative} uses AI-flavoured phrasing: {phrase!r}"


def test_the_copy_uses_the_campaign_offer_not_the_older_locked_brief():
    """The price is $89 per seat per month plus $500 setup, everywhere. The
    older $49 / $99 seat rates and $750 onboarding were retired on 2026-09-06
    (BLOCKED.md B8, resolved). This test fails if they reappear in the copy.
    """
    for relative in ALL_FILES:
        text = _message_text(relative)
        for stale in ("$49", "$99", "$750", "49 dollar", "99 dollar", "750 dollar",
                      "49 doleri", "99 doleri", "750 doleri", "half price"):
            assert stale not in text, f"{relative} quotes the superseded price {stale!r}"


# Phrasings that present the modelled ROI figures as something observed with
# customers. The figures may appear as a worked example framed as a model; they
# may never be attributed to firms, teams or customers as a result.
MEASURED_CLAIMS = {
    "linkedin/en.md": ("firms running it are saving", "teams running it save",
                       "customers save", "customers are saving"),
    "email/en.md": ("firms running it are saving", "teams running it save",
                    "customers save", "customers are saving"),
    "phone/en.md": ("firms running it are saving", "teams running it save",
                    "customers save", "what i do have is the numbers"),
    "linkedin/da.md": ("firmaer, der kører det, sparer", "kunder sparer",
                       "kunderne sparer"),
    "phone/da.md": ("firmaer, der kører det, sparer", "kunder sparer",
                    "det, jeg har, er tallene"),
    "linkedin/lt.md": ("įmonės, kurios tai naudoja, sutaupo", "klientai sutaupo"),
    "phone/lt.md": ("įmonės, kurios tai naudoja, sutaupo", "klientai sutaupo",
                    "turiu skaičius:"),
}

# The word that has to sit next to the figures, per language, so a reader is
# told in the same message that they are looking at a model.
MODEL_WORD = {"en": "model", "da": "model", "lt": "model"}


@pytest.mark.parametrize("relative", ALL_FILES)
def test_the_roi_figures_are_framed_as_a_model_not_a_measurement(relative):
    """Decided 2026-09-06: roughly 9x, about 400 euro a month and payback in
    about 40 days are MODELLED from assumed time saved, not measured with any
    customer. The message text may quote them only as a model, and may never
    say that firms are saving or seeing them."""
    text = _message_text(relative)
    for phrase in MEASURED_CLAIMS[relative]:
        assert phrase not in text, (
            f"{relative} presents the modelled ROI figures as measured: {phrase!r}")
    if "400 euro" in text or "400 eurų" in text:
        _, locale = EXPECTED[relative]
        assert MODEL_WORD[locale] in text, (
            f"{relative} quotes the 400 euro figure without calling it a model")
