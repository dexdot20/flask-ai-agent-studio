from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from image_service import analyze_uploaded_image, answer_image_question
from image_utils import normalize_image_analysis


class TestImageService(unittest.TestCase):
    def test_analyze_uploaded_image_preserves_provider_failures(self):
        with patch("image_service.IMAGE_UPLOADS_ENABLED", True), patch(
            "image_service._resolve_processing_plan",
            return_value=["llm_helper"],
        ), patch(
            "image_service._run_helper_llm_image_analysis",
            side_effect=Exception("provider down"),
        ):
            with self.assertRaises(Exception) as raised:
                analyze_uploaded_image(
                    b"fake image bytes",
                    "image/png",
                    model_id="openrouter:anthropic/claude-sonnet-4.5",
                    processing_method="llm_helper",
                )

        self.assertEqual(type(raised.exception), Exception)
        self.assertEqual(str(raised.exception), "provider down")

    def test_analyze_uploaded_image_direct_mode_returns_passthrough_metadata(self):
        with patch("image_service.IMAGE_UPLOADS_ENABLED", True), patch(
            "image_service.can_model_process_images",
            return_value=True,
        ):
            analysis = analyze_uploaded_image(
                b"fake image bytes",
                "image/png",
                model_id="openrouter:test-vision",
                processing_method="llm_direct",
            )

        self.assertEqual(analysis["analysis_method"], "llm_direct")
        self.assertIn("attached directly", analysis["assistant_guidance"])

    def test_analyze_uploaded_image_helper_mode_falls_back_to_direct_mode(self):
        with patch("image_service.IMAGE_UPLOADS_ENABLED", True), patch(
            "image_service.can_answer_image_questions",
            return_value=False,
        ), patch(
            "image_service.can_model_process_images",
            return_value=True,
        ):
            analysis = analyze_uploaded_image(
                b"fake image bytes",
                "image/png",
                model_id="openrouter:test-vision",
                processing_method="llm_helper",
            )

        self.assertEqual(analysis["analysis_method"], "llm_direct")

    def test_analyze_uploaded_image_local_ocr_does_not_fall_back_to_remote_modes(self):
        with patch("image_service.IMAGE_UPLOADS_ENABLED", True), patch(
            "image_service._run_local_ocr_analysis",
            side_effect=RuntimeError("OCR stack unavailable"),
        ), patch(
            "image_service._prepare_direct_multimodal_analysis",
            return_value={"analysis_method": "llm_direct"},
        ) as mocked_direct, patch(
            "image_service._run_helper_llm_image_analysis",
            return_value={"analysis_method": "llm_helper"},
        ) as mocked_helper:
            with self.assertRaises(RuntimeError) as raised:
                analyze_uploaded_image(
                    b"fake image bytes",
                    "image/png",
                    processing_method="local_ocr",
                )

        self.assertEqual(str(raised.exception), "OCR stack unavailable")
        mocked_direct.assert_not_called()
        mocked_helper.assert_not_called()

    def test_normalize_image_analysis_preserves_explicit_guidance_and_method(self):
        analysis = normalize_image_analysis(
            {
                "analysis_method": "llm_helper",
                "ocr_text": "Toplam 42",
                "vision_summary": "A checkout screen with totals is visible.",
                "assistant_guidance": "Use the totals and selected shipping option.",
                "key_points": ["Total is emphasized", "Shipping option is selected"],
            }
        )

        self.assertEqual(analysis["analysis_method"], "llm_helper")
        self.assertEqual(analysis["assistant_guidance"], "Use the totals and selected shipping option.")

    def test_analyze_uploaded_image_logs_full_raw_request_payload_and_context(self):
        fake_response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"vision_summary":"Scene","key_points":["A"],"assistant_guidance":"Use it."}'
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=6, total_tokens=18),
        )

        with patch("image_service.IMAGE_UPLOADS_ENABLED", True), patch(
            "image_service._resolve_processing_plan",
            return_value=["llm_helper"],
        ), patch(
            "image_service.optimize_image_for_processing",
            return_value=(b"img-bytes", "image/png"),
        ), patch(
            "image_service.resolve_model_target",
            return_value={
                "api_model": "openrouter:test-vision",
                "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: fake_response))),
                "record": {"provider": "openrouter"},
            },
        ), patch(
            "image_service._resolve_helper_model_id",
            return_value="openrouter:test-vision",
        ), patch(
            "image_service.can_model_use_structured_outputs",
            return_value=False,
        ), patch(
            "activity_service.log_activity_call",
        ) as mocked_log:
            analyze_uploaded_image(
                b"fake image bytes",
                "image/png",
                user_text="describe this",
                model_id="openrouter:test-vision",
                processing_method="llm_helper",
                conversation_id=42,
                source_message_id=77,
            )

        self.assertTrue(mocked_log.called)
        logged_kwargs = mocked_log.call_args.kwargs
        self.assertEqual(logged_kwargs["conversation_id"], 42)
        self.assertEqual(logged_kwargs["source_message_id"], 77)
        self.assertEqual(logged_kwargs["operation"], "image_analysis")
        self.assertIn("messages", logged_kwargs["request_payload"])
        self.assertTrue(
            str(logged_kwargs["request_payload"]["messages"][0]["content"][1]["image_url"]["url"]).startswith(
                "data:image/png;base64,"
            )
        )

    def test_answer_image_question_logs_full_raw_request_payload_and_context(self):
        fake_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="The image shows a diagram."))],
            usage=SimpleNamespace(prompt_tokens=9, completion_tokens=5, total_tokens=14),
        )

        with patch(
            "image_service.optimize_image_for_processing",
            return_value=(b"img-bytes", "image/png"),
        ), patch(
            "image_service.resolve_model_target",
            return_value={
                "api_model": "openrouter:test-vision",
                "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: fake_response))),
                "record": {"provider": "openrouter"},
            },
        ), patch(
            "image_service._resolve_helper_model_id",
            return_value="openrouter:test-vision",
        ), patch(
            "activity_service.log_activity_call",
        ) as mocked_log:
            answer = answer_image_question(
                b"fake image bytes",
                "image/png",
                "What is shown?",
                initial_analysis={"vision_summary": "diagram"},
                model_id="openrouter:test-vision",
                conversation_id=9,
                source_message_id=15,
            )

        self.assertEqual(answer, "The image shows a diagram.")
        self.assertTrue(mocked_log.called)
        logged_kwargs = mocked_log.call_args.kwargs
        self.assertEqual(logged_kwargs["conversation_id"], 9)
        self.assertEqual(logged_kwargs["source_message_id"], 15)
        self.assertEqual(logged_kwargs["operation"], "image_question")
        self.assertIn("messages", logged_kwargs["request_payload"])
        self.assertTrue(
            str(logged_kwargs["request_payload"]["messages"][0]["content"][1]["image_url"]["url"]).startswith(
                "data:image/png;base64,"
            )
        )
