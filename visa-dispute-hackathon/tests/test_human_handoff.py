import unittest

from dispute_agent.human_handoff import (
    HandoffAvailability,
    HumanHandoffPolicy,
    normalize_e164,
)


class HumanHandoffPolicyTests(unittest.TestCase):
    def test_normalizes_destination_and_builds_tel_uri(self):
        policy = HumanHandoffPolicy("55 (11) 98102-0050")

        plan = policy.plan("+5511999990001")

        self.assertEqual(plan.availability, HandoffAvailability.AVAILABLE)
        self.assertEqual(plan.target_uri, "tel:+5511981020050")

    def test_rejects_self_transfer(self):
        policy = HumanHandoffPolicy("+5511981020050")

        plan = policy.plan("55 11 98102 0050")

        self.assertEqual(plan.availability, HandoffAvailability.SAME_AS_CALLER)
        self.assertFalse(plan.can_transfer)

    def test_missing_or_invalid_destination_is_unavailable(self):
        for value in (None, "", "123"):
            with self.subTest(value=value):
                plan = HumanHandoffPolicy(value).plan("+5511999990001")
                self.assertEqual(plan.availability, HandoffAvailability.NOT_CONFIGURED)

    def test_normalize_e164_accepts_only_plausible_lengths(self):
        self.assertEqual(normalize_e164("+1 (415) 555-0123"), "+14155550123")
        self.assertIsNone(normalize_e164("123"))
