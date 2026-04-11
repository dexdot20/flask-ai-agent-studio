from __future__ import annotations

import unittest
from unittest.mock import patch

from image_service import analyze_uploaded_image
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
