"""
Voice application service.

What it does:
- Orchestrates speech synthesis and voice profile resolution.
- Generates speech scripts for task nudges, deadline alerts, and leaderboard reports.

What it does NOT do:
- Does NOT execute binaries or subprocesses directly (delegates to SpeechSynthesizer).
- Does NOT interact with Discord APIs directly.
"""

from typing import Optional
from src.domain.entities.voice_profile import VoiceProfile
from src.domain.interfaces.speech_synthesizer import SpeechSynthesizer
from src.application.dtos.voice_dtos import SynthesizeRequestDTO, AudioClipDTO
from src.domain.errors import ValidationError

class VoiceService:
    """Orchestrates speech synthesis for alerts, reminders, and audio commands."""

    def __init__(self, synthesizer: SpeechSynthesizer, default_language: str = "en-us"):
        self.synthesizer = synthesizer
        self.default_language = default_language

    def resolve_profile(
        self,
        user_id: Optional[str] = None,
        tone: Optional[str] = None,
        language: Optional[str] = None
    ) -> VoiceProfile:
        """Constructs a customized VoiceProfile incorporating tone and user voice pin."""
        selected_tone = tone or "serious"
        selected_lang = language or self.default_language
        profile = VoiceProfile.from_tone(selected_tone, selected_lang)
        if user_id:
            profile = profile.with_user_offset(user_id)
        return profile

    async def synthesize(self, dto: SynthesizeRequestDTO) -> AudioClipDTO:
        """Synthesizes text into audio bytes using resolved profile."""
        clean_text = dto.text.strip()
        if not clean_text:
            raise ValidationError("Speech text cannot be empty.")

        profile = self.resolve_profile(dto.user_id, dto.tone, dto.language)
        audio_bytes = await self.synthesizer.synthesize(clean_text, profile)

        return AudioClipDTO(
            audio_bytes=audio_bytes,
            filename=f"voice_{profile.tone}_{profile.voice_name}.wav",
            transcript=clean_text,
            tone=profile.tone,
            language=profile.voice_name
        )

    def generate_task_reminder_script(
        self,
        task_id: str,
        description: str,
        assignee_name: str,
        hours_overdue: Optional[int] = None,
        is_urgent: bool = False,
        lang: str = "en-us"
    ) -> str:
        """Generates spoken reminder script for overdue items or 1h urgency."""
        if lang.lower().startswith("ru"):
            if hours_overdue:
                return (
                    f"Внимание, {assignee_name}. Задача {task_id}, {description}, "
                    f"просрочена на {hours_overdue} ч. Немедленно приступайте к работе."
                )
            elif is_urgent:
                return f"Срочное напоминание, {assignee_name}! До сдачи задачи {description} остался один час."
            else:
                return f"Напоминание для {assignee_name}. До сдачи задачи {description} осталось двадцать четыре часа."

        # Default English
        if hours_overdue:
            return (
                f"Attention {assignee_name}. Task {task_id}, {description}, "
                f"is overdue by {hours_overdue} hours! Report progress immediately."
            )
        elif is_urgent:
            return f"Urgent alert for {assignee_name}. Task {description} is due in under one hour!"
        else:
            return f"Friendly reminder for {assignee_name}. Task {description} is due in twenty-four hours."

    def generate_deadline_alert_script(self, name: str, tier: str, lang: str = "en-us") -> str:
        """Generates spoken milestone alert script."""
        if lang.lower().startswith("ru"):
            if tier == "0h":
                return f"Внимание команде. Дедлайн {name} наступил! Все материалы должны быть загружены."
            elif tier == "6h":
                return f"Внимание команде! До важной контрольной точки {name} осталось шесть часов."
            else:
                return f"Напоминание о майлстоуне. До дедлайна {name} осталось двадцать четыре часа."

        if tier == "0h":
            return f"Attention team! Deadline for milestone {name} has expired! Finalize submissions now."
        elif tier == "6h":
            return f"High priority alert! Milestone {name} is due in under six hours."
        else:
            return f"Milestone alert. Twenty-four hours remaining until {name}."

    def generate_report_script(
        self,
        leader_name: str,
        leader_score: float,
        overdue_count: int,
        total_tasks: int,
        completed_tasks: int,
        lang: str = "en-us"
    ) -> str:
        """Generates spoken leaderboard report summary."""
        completion_pct = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0
        if lang.lower().startswith("ru"):
            status = "Внимание! Есть просроченные задачи." if overdue_count > 0 else "Все задачи в графике."
            return (
                f"Отчёт по проекту. Лидер команды — {leader_name} с результатом {leader_score:.1f} очков. "
                f"Выполнено {completed_tasks} из {total_tasks} задач, то есть {completion_pct} процентов. {status}"
            )

        status = f"Warning: {overdue_count} task(s) are currently overdue." if overdue_count > 0 else "All tasks are currently on track."
        return (
            f"Project status audio briefing. Current team leader is {leader_name} with {leader_score:.1f} points. "
            f"Overall progress: {completed_tasks} of {total_tasks} tasks completed, or {completion_pct} percent. {status}"
        )
