"""Masking and the local pipeline (mask -> triage -> review) with the stub model. Fictional data."""
import json

from alert_triage.agent.agent import triage
from alert_triage.llm import FakeModel
from alert_triage.storage import LocalStore
from alert_triage.masking.masker import Masker, unmask
from alert_triage import pipeline

NAME, OTHER, ACCT, CP_ID = "Jane Example", "Acme Holdings Ltd", "001234567", "ECP0001"


def sample_case(wid=1001):
    txn = lambda i, cp: {"TransactionId": f"T{i}", "TransactionDate": f"2020-01-{10 + i}T10:00:00", "BaseCurrencyAmount": 9000 + i,
                         "PrimaryCurrency": "CAD", "TransactionMethod": "Wire Payments", "TransactionType": "LYXCT",
                         "SecondaryEntityName": cp, "SecondaryEntityId": CP_ID, "SecondaryInstitutionName": "Other Bank",
                         "SecondaryInstitutionCountry": "CA", "PrimaryAccountId": ACCT, "TransactionDescription": f"payment from {NAME} to {cp}"}
    txns = [txn(1, OTHER), txn(2, OTHER), txn(3, "Someone Else")]
    return {
        "work_item": {"work_item_id": wid, "state": "Assigned", "assigned_to": "AML Investigator", "priority": "1"},
        "entity": {"alessa_id": "guid-1", "name": NAME, "address": "1 Main St", "phone": "604-555-0100",
                   "email": "jane@example.com", "identification_type": "Passport", "identification_value": "X1234567",
                   "country": "CA", "occupation": "Engineer", "account_type": "Personal"},
        "alerts": [{"alert_id": "A1", "rule_pattern": "Multiple Locations", "description": "2 transactions totalling $18003",
                    "triggering_transactions": txns[:2]}],
        "transactions": txns,
        "history": [{"date": "2020-02-01", "performed_by": "Analyst Person", "action": "Add Comment",
                     "comment": f"Spoke to {NAME}; payroll payments to {OTHER}."}],
        "detail_record": {"NAME": NAME, "IDENTIFICATION_TYPE": "Passport", "COUNTRY": "CA"},
        "accounts": [{"AccountId": ACCT, "AccountType": "Chequing", "Currency": "CAD"}],
        "meta": {"warnings": []},
    }


def test_masking_is_consistent_and_complete():
    masked, tm = Masker().mask(sample_case())
    text = json.dumps(masked)
    for secret in (NAME, OTHER, ACCT, CP_ID, "1 Main St", "604-555-0100", "jane@example.com", "X1234567", "Analyst Person"):
        assert secret not in text, secret
    # same value -> same token everywhere (counterparty of both triggering transactions)
    trig = masked["alerts"][0]["triggering_transactions"]
    assert trig[0]["SecondaryEntityName"] == trig[1]["SecondaryEntityName"].strip()
    assert masked["entity"]["name"] in masked["history"][0]["comment"]  # name inside free text replaced by its token
    # analysis fields are kept
    assert masked["entity"]["country"] == "CA" and masked["entity"]["identification_type"] == "Passport"
    assert trig[0]["SecondaryInstitutionName"] == "Other Bank" and trig[0]["TransactionMethod"] == "Wire Payments"
    # unmask restores the real values
    assert unmask(f"Reviewed {masked['entity']['name']}.", tm.to_dict()) == f"Reviewed {NAME}."


def test_model_only_sees_masked_data():
    model = FakeModel()
    masked, _ = Masker().mask(sample_case())
    r = triage(masked, model, sop_rules="Rule 1: test")
    assert r.recommendation == "needs_review"
    prompt = model.prompts[0]
    assert NAME not in prompt and OTHER not in prompt and ACCT not in prompt and CP_ID not in prompt
    assert "Multiple Locations" in prompt and "Rule 1: test" in prompt


def test_local_pipeline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("STORAGE", "local")
    store = LocalStore(tmp_path)
    for wid in (1001, 1002):
        store.put("alessa", "cases", f"{wid}.json", sample_case(wid))
    out = pipeline.main([])
    assert [o.get("recommendation") for o in out] == ["needs_review", "needs_review"]
    review = store.get("alessa", "review", "1001.json")
    assert NAME in review["draft_comment"]            # unmasked for the analyst
    assert NAME not in json.dumps(store.get("alessa", "results", "1001.json"))  # stored agent output stays masked
    assert store.list("alessa", "tokens") == ["1001.json", "1002.json"]
