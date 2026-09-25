"""Tests for make-certificate.sh, the certificate nginx serves.

The script is run for real, with openssl, into a temporary folder, never into
~/PSells-CA or data/tls. What matters most is the CA's name constraint: that
it signs for psells.localhost and for nothing else, so a leaked CA key could
not impersonate another site. That is tested the only convincing way, by
making the CA sign certificates it should not be able to, and checking that
they are refused.

openssl here is whichever is first on the PATH: OpenSSL on CI, and Homebrew
OpenSSL on the Mac. The script refuses anything else, LibreSSL included,
and a test checks that refusal with a fake openssl.
"""

import os
import shutil
import stat
import subprocess
from datetime import datetime

import pytest

import psells


SCRIPT = os.path.join(psells.PROJECT_DIR, "make-certificate.sh")
NAME = "psells.localhost"


def openssl(*arguments, check=True):
    return subprocess.run(["openssl", *arguments], capture_output=True,
                          text=True, check=check)


def run_script(ca_dir, tls_dir, path=None):
    environment = dict(os.environ, PSELLS_CA_DIR=str(ca_dir),
                       PSELLS_TLS_DIR=str(tls_dir))
    if path is not None:
        environment["PATH"] = path
    return subprocess.run(["bash", SCRIPT], capture_output=True, text=True,
                          env=environment)


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    """One run of the script: (CA folder, certificate folder, the run)."""
    assert shutil.which("openssl"), "openssl is needed to run these tests"

    base = tmp_path_factory.mktemp("tls")
    ca_dir, tls_dir = base / "ca", base / "tls"
    result = run_script(ca_dir, tls_dir)

    assert result.returncode == 0, result.stderr
    return ca_dir, tls_dir, result


def lifetime_in_days(certificate):
    dates = dict(line.split("=", 1) for line in openssl(
        "x509", "-in", str(certificate), "-noout", "-startdate", "-enddate"
    ).stdout.splitlines())

    def parse(value):
        return datetime.strptime(value.strip(), "%b %d %H:%M:%S %Y %Z")

    return (parse(dates["notAfter"]) - parse(dates["notBefore"])).days


def sign_with_the_ca(ca_dir, work, subject_alt_name):
    """A certificate the CA signs for any name at all, as a stolen key would.

    It uses the CA's key directly, the way someone holding that key would,
    rather than the script, which only ever signs for psells.localhost.
    """
    key, request, certificate, extensions = (
        work / "rogue.key", work / "rogue.csr", work / "rogue.crt",
        work / "rogue.cnf")
    extensions.write_text(f"[rogue]\nsubjectAltName = {subject_alt_name}\n")

    openssl("genpkey", "-algorithm", "EC", "-pkeyopt",
            "ec_paramgen_curve:P-256", "-out", str(key))
    openssl("req", "-new", "-key", str(key), "-subj", "/CN=rogue",
            "-out", str(request))
    openssl("x509", "-req", "-in", str(request), "-CA",
            str(ca_dir / "ca.crt"), "-CAkey", str(ca_dir / "ca.key"),
            "-set_serial", "7", "-days", "30", "-extfile", str(extensions),
            "-extensions", "rogue", "-out", str(certificate))
    return certificate


def verify(ca_dir, certificate):
    return openssl("verify", "-CAfile", str(ca_dir / "ca.crt"),
                   str(certificate), check=False)


# What it makes -----------------------------------------------------------------

def test_the_certificate_is_signed_by_the_ca(made):
    ca_dir, tls_dir, _ = made

    result = verify(ca_dir, tls_dir / f"{NAME}.crt")

    assert result.returncode == 0, result.stdout + result.stderr


def test_the_certificate_is_for_psells_localhost_and_can_sign_nothing(made):
    _, tls_dir, _ = made

    text = openssl("x509", "-in", str(tls_dir / f"{NAME}.crt"),
                   "-noout", "-text").stdout

    assert f"DNS:{NAME}" in text
    assert "IP Address" not in text
    assert "CA:FALSE" in text
    assert "TLS Web Server Authentication" in text


def test_the_certificate_matches_its_key(made):
    _, tls_dir, _ = made

    from_certificate = openssl("x509", "-in", str(tls_dir / f"{NAME}.crt"),
                               "-noout", "-pubkey").stdout
    from_key = openssl("pkey", "-in", str(tls_dir / f"{NAME}.key"),
                       "-pubout").stdout

    assert from_certificate == from_key


def test_the_certificate_lasts_397_days_and_the_ca_five_years(made):
    ca_dir, tls_dir, _ = made

    assert lifetime_in_days(tls_dir / f"{NAME}.crt") == 397
    assert lifetime_in_days(ca_dir / "ca.crt") == 1826


def test_the_ca_constraint_is_critical(made):
    ca_dir, _, _ = made

    text = openssl("x509", "-in", str(ca_dir / "ca.crt"),
                   "-noout", "-text").stdout

    assert "X509v3 Name Constraints: critical" in text
    assert "CA:TRUE, pathlen:0" in text


def test_every_key_and_folder_is_readable_by_its_owner_only(made):
    ca_dir, tls_dir, _ = made

    for path in (ca_dir, tls_dir):
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o700, path
    for path in (ca_dir / "ca.key", tls_dir / f"{NAME}.key"):
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600, path


def test_a_new_ca_comes_with_the_command_to_trust_it(made):
    ca_dir, _, result = made

    assert "security add-trusted-cert -r trustRoot" in result.stdout
    assert str(ca_dir / "ca.crt") in result.stdout


def test_every_run_says_how_to_make_nginx_use_the_new_certificate(made):
    _, _, result = made

    assert "docker compose restart proxy" in result.stdout


# What the CA refuses to vouch for ----------------------------------------------

@pytest.mark.parametrize("subject_alt_name", [
    "DNS:example.com",
    "DNS:evil.localhost",
    "DNS:localhost",
    "IP:127.0.0.1",
    "IP:::1",
])
def test_a_certificate_the_ca_signs_for_anything_else_is_refused(
        made, tmp_path, subject_alt_name):
    ca_dir, _, _ = made

    rogue = sign_with_the_ca(ca_dir, tmp_path, subject_alt_name)
    result = verify(ca_dir, rogue)

    assert result.returncode != 0, subject_alt_name
    assert "subtree violation" in result.stdout + result.stderr


def test_the_rogue_signing_itself_works(made, tmp_path):
    # Without this, every refusal above could be a certificate that failed for
    # some unrelated reason. The same signing, for the permitted name, passes.
    ca_dir, _, _ = made

    allowed = sign_with_the_ca(ca_dir, tmp_path, f"DNS:{NAME}")

    assert verify(ca_dir, allowed).returncode == 0


# Running it again --------------------------------------------------------------

def test_running_again_keeps_the_ca_and_issues_a_new_certificate(tmp_path):
    ca_dir, tls_dir = tmp_path / "ca", tmp_path / "tls"
    assert run_script(ca_dir, tls_dir).returncode == 0
    ca_before = (ca_dir / "ca.crt").read_bytes()
    certificate_before = (tls_dir / f"{NAME}.crt").read_bytes()

    again = run_script(ca_dir, tls_dir)

    assert again.returncode == 0, again.stderr
    assert (ca_dir / "ca.crt").read_bytes() == ca_before
    assert (tls_dir / f"{NAME}.crt").read_bytes() != certificate_before
    # Nothing to trust again, so no instruction to.
    assert "add-trusted-cert" not in again.stdout
    assert verify(ca_dir, tls_dir / f"{NAME}.crt").returncode == 0


def test_a_ca_that_would_expire_first_is_refused_and_nothing_changes(tmp_path):
    ca_dir, tls_dir = tmp_path / "ca", tmp_path / "tls"
    assert run_script(ca_dir, tls_dir).returncode == 0
    certificate_before = (tls_dir / f"{NAME}.crt").read_bytes()

    # Replace the CA's certificate with one for the same key that expires in
    # thirty days, sooner than any certificate the script would sign.
    openssl("req", "-new", "-x509", "-key", str(ca_dir / "ca.key"),
            "-subj", "/CN=short-lived", "-days", "30",
            "-out", str(ca_dir / "ca.crt"))

    result = run_script(ca_dir, tls_dir)

    assert result.returncode != 0
    assert "expires within 397 days" in result.stderr
    assert (tls_dir / f"{NAME}.crt").read_bytes() == certificate_before


def test_an_unreadable_ca_certificate_is_refused_and_nothing_changes(tmp_path):
    ca_dir, tls_dir = tmp_path / "ca", tmp_path / "tls"
    assert run_script(ca_dir, tls_dir).returncode == 0
    certificate_before = (tls_dir / f"{NAME}.crt").read_bytes()
    (ca_dir / "ca.crt").write_text("not a certificate")

    result = run_script(ca_dir, tls_dir)

    assert result.returncode != 0
    assert "could not read the CA certificate" in result.stderr
    assert (tls_dir / f"{NAME}.crt").read_bytes() == certificate_before


def test_half_a_ca_is_refused_rather_than_overwritten(tmp_path):
    ca_dir, tls_dir = tmp_path / "ca", tmp_path / "tls"
    ca_dir.mkdir()
    (ca_dir / "ca.key").write_text("a key whose certificate went missing")

    result = run_script(ca_dir, tls_dir)

    assert result.returncode != 0
    assert "half a CA" in result.stderr
    assert (ca_dir / "ca.key").read_text() == "a key whose certificate went missing"
    assert not tls_dir.exists()


def test_a_ca_certificate_for_another_key_is_refused_with_a_reason(tmp_path):
    ca_dir, tls_dir = tmp_path / "ca", tmp_path / "tls"
    assert run_script(ca_dir, tls_dir).returncode == 0
    certificate_before = (tls_dir / f"{NAME}.crt").read_bytes()
    key_before = (tls_dir / f"{NAME}.key").read_bytes()

    # A long-lived CA certificate for a different key, so ca.key and ca.crt no
    # longer belong together and openssl refuses to sign with the pair.
    other_key = tmp_path / "other.key"
    openssl("genpkey", "-algorithm", "EC", "-pkeyopt",
            "ec_paramgen_curve:P-256", "-out", str(other_key))
    openssl("req", "-new", "-x509", "-key", str(other_key),
            "-subj", "/CN=someone else", "-days", "1826",
            "-out", str(ca_dir / "ca.crt"))

    result = run_script(ca_dir, tls_dir)

    assert result.returncode != 0
    assert "signing with" in result.stderr
    assert (tls_dir / f"{NAME}.crt").read_bytes() == certificate_before
    assert (tls_dir / f"{NAME}.key").read_bytes() == key_before


def test_a_certificate_that_does_not_verify_replaces_nothing(tmp_path):
    ca_dir, tls_dir = tmp_path / "ca", tmp_path / "tls"
    assert run_script(ca_dir, tls_dir).returncode == 0
    certificate_before = (tls_dir / f"{NAME}.crt").read_bytes()
    key_before = (tls_dir / f"{NAME}.key").read_bytes()

    # The CA's own key, in a certificate that says it is not a CA. Signing
    # succeeds, because the key matches, and the result cannot verify, because
    # its issuer is not allowed to issue anything.
    not_a_ca = tmp_path / "not-a-ca.cnf"
    not_a_ca.write_text(
        "[req]\ndistinguished_name = dn\nprompt = no\nx509_extensions = ext\n"
        "[dn]\nCN = not a CA\n[ext]\nbasicConstraints = critical, CA:FALSE\n")
    openssl("req", "-new", "-x509", "-config", str(not_a_ca),
            "-key", str(ca_dir / "ca.key"), "-days", "1826",
            "-out", str(ca_dir / "ca.crt"))

    result = run_script(ca_dir, tls_dir)

    assert result.returncode != 0
    assert "does not verify" in result.stderr
    assert (tls_dir / f"{NAME}.crt").read_bytes() == certificate_before
    assert (tls_dir / f"{NAME}.key").read_bytes() == key_before


def test_an_openssl_that_is_not_openssl_is_refused_and_nothing_is_made(tmp_path):
    # LibreSSL, the openssl that ships with macOS, prints nothing from
    # -checkend, so the script could never read its answer on the CA's expiry.
    # A fake that answers every command as LibreSSL stands first on the PATH.
    fake = tmp_path / "bin" / "openssl"
    fake.parent.mkdir()
    fake.write_text('#!/bin/sh\necho "LibreSSL 3.3.6"\n')
    fake.chmod(0o755)
    ca_dir, tls_dir = tmp_path / "ca", tmp_path / "tls"

    result = run_script(ca_dir, tls_dir,
                        path=f"{fake.parent}{os.pathsep}{os.environ['PATH']}")

    assert result.returncode != 0
    assert "needs OpenSSL" in result.stderr
    assert "LibreSSL 3.3.6" in result.stderr
    assert not ca_dir.exists()
    assert not tls_dir.exists()


def test_folders_that_already_exist_are_closed_to_everyone_else(tmp_path):
    # mkdir under a strict umask covers a folder the script creates; a folder
    # that was already there, readable by anyone, needs its mode changed.
    ca_dir, tls_dir = tmp_path / "ca", tmp_path / "tls"
    for path in (ca_dir, tls_dir):
        path.mkdir(mode=0o755)
        os.chmod(path, 0o755)

    assert run_script(ca_dir, tls_dir).returncode == 0

    for path in (ca_dir, tls_dir):
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o700, path
