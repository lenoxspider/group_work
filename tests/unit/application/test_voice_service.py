"""Unit tests for VoiceService application service."""

import unittest
from unittest.mock import AsyncMock
from src.application.services.voice_service import VoiceService
from src.application.dtos.voice_dtos import SynthesizeRequestDTO
from src.domain.interfaces.speech_synthesizer import SpeechSynthesizer
from src.domain.errors import ValidationError

class TestVoiceService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_synthesizer = AsyncMock(spec=SpeechSynthesizer)
        self.mock_synthesizer.synthesize.return_value = b"RIFF_FAKE_WAV_BYTES"
        self.service = VoiceService(self.mock_synthesizer, default_language="en-us")

    async def test_synthesize_success(self):
        dto = SynthesizeRequestDTO(
            text="Hello world test",
            user_id="12345",
            tone="drill_sergeant",
            language="en-us"
        )
        clip = await self.service.synthesize(dto)

        self.mock_synthesizer.synthesize.assert_awaited_once()
        self.assertEqual(clip.audio_bytes, b"RIFF_FAKE_WAV_BYTES")
        self.assertEqual(clip.transcript, "Hello world test")
        self.assertEqual(clip.tone, "drill_sergeant")
        self.assertEqual(clip.language, "en-us")

    async def test_synthesize_empty_text_raises_validation_error(self):
        dto = SynthesizeRequestDTO(text="   ")
        with self.assertRaises(ValidationError):
            await self.service.synthesize(dto)

    def test_generate_task_reminder_script_english(self):
        script_overdue = self.service.generate_task_reminder_script(
            task_id="TASK-01",
            description="Write intro",
            assignee_name="Alice",
            hours_overdue=3
        )
        self.assertIn("Alice", script_overdue)
        self.assertIn("TASK-01", script_overdue)
        self.assertIn("3 hours", script_overdue)

        script_urgent = self.service.generate_task_reminder_script(
            task_id="TASK-02",
            description="Fix bug",
            assignee_name="Bob",
            is_urgent=True
        )
        self.assertIn("one hour", script_urgent)

    def test_generate_task_reminder_script_russian(self):
        script_ru = self.service.generate_task_reminder_script(
            task_id="TASK-RU",
            description="Тест документации",
            assignee_name="Иван",
            hours_overdue=5,
            lang="ru"
        )
        self.assertIn("Иван", script_ru)
        self.assertIn("просрочена", script_ru)

    def test_generate_deadline_alert_script(self):
        en_script = self.service.generate_deadline_alert_script("Final Sprint", "6h", lang="en-us")
        self.assertIn("Final Sprint", en_script)
        self.assertIn("six hours", en_script)

        ru_script = self.service.generate_deadline_alert_script("Дипломная работа", "0h", lang="ru")
        self.assertIn("наступил", ru_script)

    def test_generate_report_script(self):
        en_script = self.service.generate_report_script(
            leader_name="Alice",
            leader_score=45.5,
            overdue_count=1,
            total_tasks=10,
            completed_tasks=8,
            lang="en-us"
        )
        self.assertIn("Alice", en_script)
        self.assertIn("45.5", en_script)
        self.assertIn("80 percent", en_script)
        self.assertIn("Warning", en_script)

if __name__ == "__main__":
    unittest.main()
