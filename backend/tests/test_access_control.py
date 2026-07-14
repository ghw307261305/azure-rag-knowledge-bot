from pathlib import Path

from app.services.local_search_service import LocalSearchService

REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = REPO_ROOT / "docs" / "knowledge-finance"


def test_acl_allows_compliance_group_to_retrieve_aml_document() -> None:
    search = LocalSearchService(KNOWLEDGE_DIR)

    results = search.search(
        "疑わしい取引の検知とAMLモニタリング",
        allowed_groups={"compliance"},
    )

    assert results
    assert results[0]["source"] == "05-aml-transaction-monitoring.md"
    assert results[0]["security_level"] == "confidential"


def test_acl_excludes_restricted_documents_for_unrelated_group() -> None:
    search = LocalSearchService(KNOWLEDGE_DIR)

    results = search.search(
        "疑わしい取引の検知とAMLモニタリング",
        allowed_groups={"finance-all"},
    )

    assert all(
        result["source"]
        not in {
            "05-aml-transaction-monitoring.md",
            "06-suspicious-transaction-escalation.md",
        }
        for result in results
    )


def test_acl_is_not_applied_when_authentication_is_disabled() -> None:
    search = LocalSearchService(KNOWLEDGE_DIR)

    results = search.search("疑わしい取引の検知とAMLモニタリング")

    assert results[0]["source"] == "05-aml-transaction-monitoring.md"
