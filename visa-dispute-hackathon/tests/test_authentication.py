from pathlib import Path
import unittest

from dispute_agent.authentication import AuthenticationAgent, AuthStatus, normalize_name
from dispute_agent.intent_classifier import (
    AnswerIntent,
    ClassificationError,
    IntentDecision,
    LocalAvoidanceClassifier,
)


FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class FakeIntentClassifier:
    def __init__(self, decisions=None, error=False):
        self.decisions = decisions or {}
        self.error = error

    def classify(self, answer):
        if self.error:
            raise ClassificationError("offline")
        intent, confidence = self.decisions.get(answer, (AnswerIntent.PROVIDES_NAME, 0.99))
        return IntentDecision(intent, confidence, {intent.value: 1.0})


def make_agent(**kwargs):
    classifier = kwargs.pop("classifier", FakeIntentClassifier())
    return AuthenticationAgent(FIXTURE, classifier, **kwargs)


class AuthenticationAgentTests(unittest.TestCase):
    def test_initial_question_asks_for_full_name(self):
        result = make_agent().start()
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertEqual(result.message, "What is your full name?")

    def test_unique_full_name_authenticates(self):
        result = make_agent().handle_answer("Ana Silva")
        self.assertTrue(result.authenticated)
        self.assertEqual(result.customer.customer_id, "CLI-002")
        self.assertEqual(result.assurance_level, "DEMO_ONLY_NAME_MATCH")

    def test_matching_ignores_case_accents_and_extra_spaces(self):
        result = make_agent().handle_answer("  JOSE   MARIA PEREZ LOPEZ ")
        self.assertTrue(result.authenticated)
        self.assertEqual(result.customer.customer_id, "CLI-001")

    def test_unknown_name_is_not_authenticated(self):
        result = make_agent().handle_answer("Person Who Does Not Exist")
        self.assertEqual(result.status, AuthStatus.NOT_FOUND)
        self.assertFalse(result.authenticated)

    def test_second_unknown_name_routes_to_human(self):
        agent = make_agent()
        agent.handle_answer("Unknown One")
        result = agent.handle_answer("Unknown Two")
        self.assertEqual(result.status, AuthStatus.HUMAN_HANDOFF)

    def test_duplicate_name_is_ambiguous(self):
        result = make_agent().handle_answer("Alex Santos")
        self.assertEqual(result.status, AuthStatus.AMBIGUOUS)
        self.assertFalse(result.authenticated)

    def test_empty_answer_is_treated_as_avoidance(self):
        result = make_agent().handle_answer("")
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("need your full name", result.message)

    def test_avoidance_is_reprompted_then_handed_off(self):
        classifier = FakeIntentClassifier({
            "Why do you need that?": (AnswerIntent.ASKS_WHY, 0.96),
            "I prefer not to say": (AnswerIntent.AVOIDS_ANSWER, 0.98),
        })
        agent = make_agent(classifier=classifier)
        first = agent.handle_answer("Why do you need that?")
        second = agent.handle_answer("I prefer not to say")
        self.assertEqual(first.status, AuthStatus.NEEDS_NAME)
        self.assertEqual(second.status, AuthStatus.HUMAN_HANDOFF)

    def test_normalization_is_deterministic(self):
        self.assertEqual(normalize_name(" José  Muñoz "), "jose munoz")

    def test_request_for_human_hands_off_immediately(self):
        classifier = FakeIntentClassifier({
            "Give me a human": (AnswerIntent.REQUESTS_HUMAN, 0.99),
        })
        result = make_agent(classifier=classifier).handle_answer("Give me a human")
        self.assertEqual(result.status, AuthStatus.HUMAN_HANDOFF)

    def test_low_confidence_classifier_result_reprompts(self):
        classifier = FakeIntentClassifier({
            "Maybe Ana": (AnswerIntent.PROVIDES_NAME, 0.30),
        })
        result = make_agent(classifier=classifier).handle_answer("Maybe Ana")
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("not sure", result.message)

    def test_classifier_failure_fails_closed_to_human(self):
        result = make_agent(classifier=FakeIntentClassifier(error=True)).handle_answer("I will not answer")
        self.assertEqual(result.status, AuthStatus.HUMAN_HANDOFF)

    def test_exact_customer_match_does_not_depend_on_classifier(self):
        result = make_agent(classifier=FakeIntentClassifier(error=True)).handle_answer("Ana Silva")
        self.assertTrue(result.authenticated)

    def test_local_model_maps_ranked_labels_to_intents(self):
        class FakePipeline:
            def __call__(self, text, **kwargs):
                labels = kwargs["candidate_labels"]
                preferred = LocalAvoidanceClassifier.LABELS[AnswerIntent.AVOIDS_ANSWER]
                ranked = [preferred] + [label for label in labels if label != preferred]
                return {"labels": ranked, "scores": [0.82, 0.08, 0.05, 0.03, 0.02]}

        classifier = LocalAvoidanceClassifier(pipeline_instance=FakePipeline())
        result = classifier.classify("I prefer not to say")
        self.assertEqual(result.intent, AnswerIntent.AVOIDS_ANSWER)
        self.assertEqual(result.confidence, 0.82)
        self.assertEqual(set(result.probabilities), {intent.value for intent in AnswerIntent})


if __name__ == "__main__":
    unittest.main()
