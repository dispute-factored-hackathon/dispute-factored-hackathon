import unittest
from pathlib import Path

from dispute_agent.caller_identity import (
    CallerIdentityStatus,
    VoiceCallerIdentityService,
    calling_code_from_phone,
    normalize_document,
    normalize_phone,
)

FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class VoiceCallerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.service = VoiceCallerIdentityService(FIXTURE)

    def test_known_phone_authenticates_unique_customer(self):
        result = self.service.identify_phone("+55 (11) 99999-0001")
        self.assertEqual(result.status, CallerIdentityStatus.AUTHENTICATED)
        self.assertEqual(result.identity.customer_id, "CLI-002")
        self.assertEqual(result.identity.detected_accent, "brazilian")
        self.assertEqual(result.identity.assurance_level, "DEMO_ONLY_PHONE_MATCH")
        self.assertEqual(result.country_code, "+55")

    def test_unknown_phone_requires_document_and_preserves_country_hint(self):
        result = self.service.identify_phone("+57 300 999 8877")
        self.assertEqual(result.status, CallerIdentityStatus.NEEDS_DOCUMENT)
        self.assertEqual(result.country_code, "+57")
        self.assertIsNone(result.identity)

    def test_document_fallback_authenticates(self):
        result = self.service.identify_document("cpf-456")
        self.assertEqual(result.status, CallerIdentityStatus.AUTHENTICATED)
        self.assertEqual(result.identity.customer_id, "CLI-002")
        self.assertEqual(result.identity.assurance_level, "DEMO_ONLY_DOCUMENT_MATCH")

    def test_unknown_document_does_not_authenticate(self):
        result = self.service.identify_document("NOT-THERE")
        self.assertEqual(result.status, CallerIdentityStatus.NOT_FOUND)
        self.assertIsNone(result.identity)

    def test_normalizers_are_deterministic(self):
        self.assertEqual(normalize_phone("+351 91 111 2222"), "+351911112222")
        self.assertEqual(calling_code_from_phone("+351 91 111 2222"), "+351")
        self.assertEqual(normalize_document(" CPF-456 "), "cpf456")

    def test_invalid_phone_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.identify_phone("123")


if __name__ == "__main__":
    unittest.main()
