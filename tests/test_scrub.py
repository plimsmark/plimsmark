"""Tests for the public-release secret/PII scanner (pure function)."""

from probe.scrub import scan


def _cats(hits):
    return {h["category"] for h in hits}


def test_github_and_openai_tokens():
    hits = scan("token=ghp_ABCDEF1234567890 and sk-abc123XYZ and gho_zzz999")
    assert _cats(hits) == {"token"}
    assert len(hits) == 3


def test_bearer_and_api_key_and_secret_words():
    hits = scan("Authorization: Bearer abc.def\napi_key: 12\nmy secret\npassword=hunter2")
    cats = [h["category"] for h in hits]
    assert cats.count("token") >= 4  # bearer, api_key, secret, password


def test_local_paths():
    hits = scan("/Users/fadhlan/x\n/home/bob/y\n/private/tmp/z")
    assert _cats(hits) == {"local_path"}
    lines = sorted(h["line"] for h in hits)
    assert lines == [1, 2, 3]


def test_email_addresses():
    hits = scan("contact me at alice.b+tag@example.co.uk please")
    assert _cats(hits) == {"email"}
    assert "alice.b+tag@example.co.uk" in hits[0]["snippet"]


def test_private_ip_ranges_hit_but_public_does_not():
    hits = scan("10.0.0.5 192.168.1.1 172.16.9.9 127.0.0.1 169.254.1.1 but 93.184.216.34 is public")
    assert _cats(hits) == {"private_ip"}
    matched = {h["match"] for h in hits}
    assert "10.0.0.5" in matched
    assert "192.168.1.1" in matched
    assert "172.16.9.9" in matched
    assert "127.0.0.1" in matched
    assert "93.184.216.34" not in matched


def test_version_strings_are_not_private_ips():
    hits = scan("httpx 0.28.1 and python 3.11 and checkpoint 327453834")
    assert not any(h["category"] == "private_ip" for h in hits)


def test_hostname_match_when_provided():
    hits = scan("running on Fadhlans-MacBook-Pro.local today", hostname="Fadhlans-MacBook-Pro.local")
    assert _cats(hits) == {"hostname"}


def test_hostname_not_flagged_when_not_provided():
    assert scan("running on some-host today") == []


def test_clean_text_has_no_hits():
    assert scan("Sui GraphQL returns 1416 events; MoveEventType filter agrees.") == []


def test_line_numbers_are_one_indexed():
    hits = scan("clean line\nghp_secrettoken0000\n")
    assert hits[0]["line"] == 2
