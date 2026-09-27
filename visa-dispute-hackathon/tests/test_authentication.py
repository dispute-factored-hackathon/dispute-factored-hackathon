from pathlib import Path
import unittest

from dispute_agent.authentication import AuthenticationAgent, AuthStatus, normalize_name
from dispute_agent.intent_classifier import (
    AnswerIntent,
    ClassificationError,
    ConfirmationDecision,
    ConfirmationIntent,
    IntentDecision,
    LocalAvoidanceClassifier,
    LocalConfirmationClassifier,
)
from dispute_agent.language_classifier import (
    LanguageClassificationError,
    LanguageDecision,
    LocalLanguageClassifier,
)
from dispute_agent.name_extractor import LocalLLMNameExtractor, NameExtractionError


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


class FakeLanguageClassifier:
    def __init__(self, decisions=None, error=False):
        self.decisions = decisions or {}
        self.error = error

    def classify(self, text):
        if self.error:
            raise LanguageClassificationError("offline")
        language, confidence = self.decisions.get(text, ("en", 0.99))
        return LanguageDecision(language, confidence)


class FakeNameExtractor:
    def __init__(self, values=None, error=False):
        self.values = values or {}
        self.error = error

    def extract(self, text):
        if self.error:
            raise NameExtractionError("offline")
        return self.values.get(text)


class FakeConfirmationClassifier:
    def __init__(self, decisions=None, confidence=0.99):
        self.decisions = decisions or {}
        self.confidence = confidence

    def classify(self, answer):
        intent = self.decisions.get(answer, ConfirmationIntent.OTHER)
        remaining = (1.0 - self.confidence) / 2
        probabilities = {candidate.value: remaining for candidate in ConfirmationIntent}
        probabilities[intent.value] = self.confidence
        return ConfirmationDecision(intent, self.confidence, probabilities)


def make_agent(**kwargs):
    classifier = kwargs.pop("classifier", FakeIntentClassifier())
    return AuthenticationAgent(FIXTURE, classifier, **kwargs)


class AuthenticationAgentTests(unittest.TestCase):
    def test_initial_question_asks_for_full_name(self):
        result = make_agent().start()
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("card dispute", result.message)
        self.assertIn("full name", result.message)

    def test_unique_full_name_authenticates(self):
        result = make_agent().handle_answer("Ana Silva")
        self.assertTrue(result.authenticated)
        self.assertEqual(result.customer.customer_id, "CLI-002")
        self.assertEqual(result.assurance_level, "DEMO_ONLY_NAME_MATCH")

    def test_found_name_requires_confirmation_when_classifier_is_enabled(self):
        classifier = FakeConfirmationClassifier({"sim": ConfirmationIntent.CONFIRMS})
        agent = make_agent(language="pt", confirmation_classifier=classifier)

        proposed = agent.handle_answer("Ana Silva")
        confirmed = agent.handle_answer("sim")

        self.assertEqual(proposed.status, AuthStatus.NEEDS_CONFIRMATION)
        self.assertIn("Ana Silva", proposed.message)
        self.assertIn("sim ou não", proposed.message)
        self.assertTrue(confirmed.authenticated)
        self.assertEqual(confirmed.customer.customer_id, "CLI-002")
        self.assertEqual(confirmed.assurance_level, "DEMO_ONLY_NAME_MATCH_CONFIRMED")

    def test_denied_name_asks_for_correct_name(self):
        classifier = FakeConfirmationClassifier({"não": ConfirmationIntent.DENIES})
        agent = make_agent(language="pt", confirmation_classifier=classifier)
        agent.handle_answer("Ana Silva")

        result = agent.handle_answer("não")

        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("nome completo correto", result.message)

    def test_denial_with_correction_looks_up_corrected_name_in_same_turn(self):
        answer = "não, meu nome é José María Pérez López"
        # A long correction can confuse zero-shot classification; the explicitly
        # extracted different name must still take precedence.
        classifier = FakeConfirmationClassifier({answer: ConfirmationIntent.CONFIRMS})
        extractor = FakeNameExtractor({answer: "José María Pérez López"})
        agent = make_agent(
            language="pt",
            confirmation_classifier=classifier,
            name_extractor=extractor,
        )
        agent.handle_answer("Ana Silva")

        result = agent.handle_answer(answer)

        self.assertEqual(result.status, AuthStatus.NEEDS_CONFIRMATION)
        self.assertIn("José María Pérez López", result.message)

    def test_other_confirmation_response_explains_required_answer(self):
        classifier = FakeConfirmationClassifier({"talvez": ConfirmationIntent.OTHER})
        agent = make_agent(language="pt", confirmation_classifier=classifier)
        agent.handle_answer("Ana Silva")

        result = agent.handle_answer("talvez")

        self.assertEqual(result.status, AuthStatus.NEEDS_CONFIRMATION)
        self.assertIn("Ana Silva", result.message)
        self.assertIn("sim ou não", result.message)

    def test_matching_ignores_case_accents_and_extra_spaces(self):
        result = make_agent().handle_answer("  JOSE   MARIA PEREZ LOPEZ ")
        self.assertTrue(result.authenticated)
        self.assertEqual(result.customer.customer_id, "CLI-001")

    def test_llm_extracts_name_from_natural_portuguese_response(self):
        answer = "meu nome é josé maría pérez lópez"
        extractor = FakeNameExtractor({answer: "josé maría pérez lópez"})
        result = make_agent(name_extractor=extractor).handle_answer(answer)
        self.assertTrue(result.authenticated)
        self.assertEqual(result.customer.customer_id, "CLI-001")

    def test_llm_extraction_overrides_other_intent_for_grounded_name(self):
        answer = "meu nome é josé maría pérez lópez"
        classifier = FakeIntentClassifier({
            answer: (AnswerIntent.OTHER, 0.98),
        })
        extractor = FakeNameExtractor({answer: "josé maría pérez lópez"})
        result = make_agent(
            classifier=classifier,
            name_extractor=extractor,
        ).handle_answer(answer)
        self.assertTrue(result.authenticated)
        self.assertEqual(result.customer.customer_id, "CLI-001")

    def test_llm_extraction_overrides_low_confidence_intent_for_grounded_name(self):
        answer = "meu nome é josé maría pérez lópez"
        classifier = FakeIntentClassifier({
            answer: (AnswerIntent.PROVIDES_NAME, 0.30),
        })
        extractor = FakeNameExtractor({answer: "josé maría pérez lópez"})
        result = make_agent(
            classifier=classifier,
            name_extractor=extractor,
        ).handle_answer(answer)
        self.assertTrue(result.authenticated)
        self.assertEqual(result.customer.customer_id, "CLI-001")

    def test_name_extraction_failure_falls_back_without_authenticating(self):
        result = make_agent(name_extractor=FakeNameExtractor(error=True)).handle_answer(
            "meu nome é uma pessoa inexistente"
        )
        self.assertEqual(result.status, AuthStatus.NOT_FOUND)

    def test_unknown_name_is_not_authenticated(self):
        result = make_agent().handle_answer("Person Who Does Not Exist")
        self.assertEqual(result.status, AuthStatus.NOT_FOUND)
        self.assertFalse(result.authenticated)
        self.assertIn("Person Who Does Not Exist", result.message)

    def test_unknown_standalone_name_gets_database_feedback_even_with_low_confidence(self):
        answer = "lelia gonzales"
        classifier = FakeIntentClassifier({
            answer: (AnswerIntent.OTHER, 0.30),
        })
        result = make_agent(
            classifier=classifier,
            language="pt",
            name_extractor=FakeNameExtractor(),
        ).handle_answer(answer)
        self.assertEqual(result.status, AuthStatus.NOT_FOUND)
        self.assertIn("Entendi o nome como lelia gonzales", result.message)
        self.assertIn("não o encontrei na base de clientes", result.message)

    def test_unclear_feedback_explains_what_was_missing(self):
        answer = "talvez depois"
        classifier = FakeIntentClassifier({
            answer: (AnswerIntent.OTHER, 0.30),
        })
        result = make_agent(
            classifier=classifier,
            language="pt",
            name_extractor=FakeNameExtractor(),
        ).handle_answer(answer)
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("identificar um nome completo", result.message)
        self.assertIn("Meu nome completo é Ana Silva", result.message)

    def test_third_unknown_name_routes_to_human_with_summary(self):
        agent = make_agent()
        agent.handle_answer("Unknown One")
        agent.handle_answer("Unknown Two")
        result = agent.handle_answer("Unknown Three")
        self.assertEqual(result.status, AuthStatus.HUMAN_HANDOFF)
        self.assertEqual(result.handoff_summary["reason"], "name_not_found_after_retries")

    def test_duplicate_name_is_ambiguous(self):
        result = make_agent().handle_answer("Alex Santos")
        self.assertEqual(result.status, AuthStatus.HUMAN_HANDOFF)
        self.assertEqual(result.handoff_summary["reason"], "duplicate_name")
        self.assertFalse(result.authenticated)

    def test_empty_answer_is_treated_as_avoidance(self):
        result = make_agent().handle_answer("")
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("did not hear", result.message)

    def test_repeated_silence_checks_audio_before_handoff(self):
        agent = make_agent()
        first = agent.handle_answer("")
        second = agent.handle_answer("")
        third = agent.handle_answer("")
        self.assertIn("did not hear", first.message)
        self.assertIn("audio or connection", second.message)
        self.assertEqual(third.status, AuthStatus.HUMAN_HANDOFF)
        self.assertEqual(third.handoff_summary["reason"], "repeated_no_response")

    def test_avoidance_is_reprompted_then_handed_off(self):
        classifier = FakeIntentClassifier({
            "Why do you need that?": (AnswerIntent.ASKS_WHY, 0.96),
            "I prefer not to say": (AnswerIntent.AVOIDS_ANSWER, 0.98),
        })
        agent = make_agent(classifier=classifier)
        first = agent.handle_answer("Why do you need that?")
        second = agent.handle_answer("I prefer not to say")
        third = agent.handle_answer("I prefer not to say")
        self.assertEqual(first.status, AuthStatus.NEEDS_NAME)
        self.assertEqual(second.status, AuthStatus.NEEDS_NAME)
        self.assertEqual(third.status, AuthStatus.HUMAN_HANDOFF)

    def test_privacy_question_is_answered_without_consuming_avoidance_budget(self):
        classifier = FakeIntentClassifier({
            "Why do you need that?": (AnswerIntent.ASKS_WHY, 0.96),
        })
        agent = make_agent(classifier=classifier)
        result = agent.handle_answer("Why do you need that?")
        self.assertIn("only to locate", result.message)
        self.assertEqual(agent.avoidance_attempts, 0)

    def test_portuguese_human_request_stays_in_portuguese(self):
        classifier = FakeIntentClassifier({
            "Quero falar com um atendente": (AnswerIntent.REQUESTS_HUMAN, 0.99),
        })
        language_classifier = FakeLanguageClassifier({
            "Quero falar com um atendente": ("pt", 0.98),
        })
        result = make_agent(
            classifier=classifier,
            language="auto",
            language_classifier=language_classifier,
        ).handle_answer("Quero falar com um atendente")
        self.assertIn("atendente", result.message)
        self.assertEqual(result.handoff_summary["language"], "pt")

    def test_auto_mode_first_asks_for_language_then_uses_selection(self):
        agent = make_agent(language="auto")
        self.assertIn("Português", agent.start().message)
        result = agent.handle_answer("Português, por favor")
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("nome completo", result.message)

    def test_auto_mode_uses_country_specific_opening(self):
        agent = make_agent(language="auto", country_code="+55")
        message = agent.start().message
        self.assertIn("Brasil", message)
        self.assertIn("português, inglês ou espanhol", message)

    def test_auto_mode_accepts_natural_spanish_language_selection(self):
        agent = make_agent(language="auto")
        result = agent.handle_answer("Español, por favor")
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("nombre completo", result.message)

    def test_auto_mode_repeats_menu_for_unknown_language_choice(self):
        agent = make_agent(language="auto")
        result = agent.handle_answer("maybe later")
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("Não reconheci", result.message)
        self.assertEqual(agent.language, "auto")

    def test_spanish_privacy_question_stays_in_spanish(self):
        classifier = FakeIntentClassifier({
            "¿Por qué necesitan mi nombre?": (AnswerIntent.ASKS_WHY, 0.99),
        })
        language_classifier = FakeLanguageClassifier({
            "¿Por qué necesitan mi nombre?": ("es", 0.98),
        })
        result = make_agent(
            classifier=classifier,
            language="auto",
            language_classifier=language_classifier,
        ).handle_answer("¿Por qué necesitan mi nombre?")
        self.assertIn("Uso tu nombre", result.message)
        self.assertNotIn("I use", result.message)

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
        self.assertIn("could not identify a full name", result.message)
        self.assertIn("My full name is Ana Silva", result.message)

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
        result = classifier.classify("This response cannot be interpreted directly")
        self.assertEqual(result.intent, AnswerIntent.AVOIDS_ANSWER)
        self.assertEqual(result.confidence, 0.82)
        self.assertEqual(set(result.probabilities), {intent.value for intent in AnswerIntent})

    def test_zero_shot_confirmation_model_maps_ranked_labels(self):
        class FakePipeline:
            def __call__(self, text, **kwargs):
                labels = kwargs["candidate_labels"]
                preferred = LocalConfirmationClassifier.LABELS[ConfirmationIntent.DENIES]
                ranked = [preferred] + [label for label in labels if label != preferred]
                return {"labels": ranked, "scores": [0.88, 0.08, 0.04]}

        base = LocalAvoidanceClassifier(pipeline_instance=FakePipeline())
        classifier = LocalConfirmationClassifier(base)
        result = classifier.classify("Não, esse não é meu nome")
        self.assertEqual(result.intent, ConfirmationIntent.DENIES)
        self.assertEqual(result.confidence, 0.88)

    def test_explicit_multilingual_human_request_does_not_load_model(self):
        classifier = LocalAvoidanceClassifier()
        result = classifier.classify("Quero falar com um atendente")
        self.assertEqual(result.intent, AnswerIntent.REQUESTS_HUMAN)
        self.assertEqual(result.confidence, 0.99)

    def test_statistical_language_model_maps_supported_language(self):
        class FakeIdentifier:
            def classify(self, text):
                return "pt", 0.93

        classifier = LocalLanguageClassifier(identifier_instance=FakeIdentifier())
        result = classifier.classify("Quero contestar uma compra")
        self.assertEqual(result.language, "pt")
        self.assertEqual(result.confidence, 0.93)

    def test_llm_name_extractor_accepts_only_grounded_multiword_name(self):
        class FakePipeline:
            def __call__(self, prompt, **kwargs):
                return [{"generated_text": "Lélia Gonzales"}]

        extractor = LocalLLMNameExtractor(pipeline_instance=FakePipeline())
        self.assertEqual(
            extractor.extract("meu nome é Lélia Gonzales"),
            "Lélia Gonzales",
        )

    def test_llm_name_extractor_rejects_hallucinated_name(self):
        class FakePipeline:
            def __call__(self, prompt, **kwargs):
                return [{"generated_text": "Maria Inventada"}]

        extractor = LocalLLMNameExtractor(pipeline_instance=FakePipeline())
        self.assertIsNone(extractor.extract("meu nome é Lélia Gonzales"))

    def test_llm_name_extractor_grounds_minor_model_typo_in_original_span(self):
        class FakePipeline:
            def __call__(self, prompt, **kwargs):
                return [{"generated_text": "samuel andrés daz pérez"}]

        extractor = LocalLLMNameExtractor(pipeline_instance=FakePipeline())
        self.assertEqual(
            extractor.extract("meu nome é samuel andrés díaz pérez"),
            "samuel andrés díaz pérez",
        )

    def test_low_confidence_language_detection_repeats_menu(self):
        agent = make_agent(
            language="auto",
            language_classifier=FakeLanguageClassifier({"hola": ("es", 0.40)}),
        )
        result = agent.handle_answer("hola")
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("No reconocí", result.message)


if __name__ == "__main__":
    unittest.main()
