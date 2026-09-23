from __future__ import annotations
import json
from orch.core.audit import canonical_json_bytes, canonical_certificate_bytes, verify_certificate_digest, scan_secrets


def test_certificate_hash_is_independent_of_pretty_printing() -> None:
    payload={'b':2,'a':{'x':1}}
    assert canonical_json_bytes(payload)==canonical_json_bytes(json.loads(json.dumps(payload,indent=4)))


def test_certificate_digest_detects_mutation() -> None:
    payload={'head_sha':'a'*40,'disposition':'PASS'}
    cert=canonical_certificate_bytes(payload)
    assert verify_certificate_digest(payload,cert.sha256)
    payload['head_sha']='b'*40
    assert not verify_certificate_digest(payload,cert.sha256)


def test_secret_scan_detects_private_key_and_env() -> None:
    findings=scan_secrets('diff --git a/.env b/.env\n+TOKEN=x\n+-----BEGIN PRIVATE KEY-----')
    assert any(f.rule_id=='PRIVATE_KEY' for f in findings)
    assert any(f.rule_id=='ENV_FILE' for f in findings)
