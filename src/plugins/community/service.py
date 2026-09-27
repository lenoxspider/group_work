"""Community application service - onboarding, the constitution gate, and the tribunal."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.application.dtos.task_dtos import CreateTaskDTO
from src.domain.errors import ValidationError
from src.plugins.community.domain import (
    CASE_ACQUITTED,
    CASE_CONVICTED,
    CASE_LAPSED,
    CASE_OPEN,
    CATIZEN,
    CITIZEN,
    COURT_APPEAL_WINDOW_HOURS,
    COURT_FALSE_WITNESS_FINE,
    COURT_QUORUM,
    COURT_VOTE_WINDOW_HOURS,
    Case,
    Member,
    utcnow,
)
from src.plugins.community.repository import SQLiteCommunityRepository

logger = logging.getLogger("plugins.community.service")

INTRO_TASK_DESCRIPTION = "Introduce yourself in #new-recruits"
INTRO_TASK_DUE_DAYS = 7


def _age_hours(ts: Optional[str]) -> Optional[float]:
    if not ts:
        return None
    try:
        then = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600.0


class CommunityService:
    def __init__(self, repo: SQLiteCommunityRepository):
        self.repo = repo
        self.bank = None
        self.task_service = None
        self.society = None

    def attach_bank(self, bank) -> None:
        self.bank = bank

    def attach_task_service(self, task_service) -> None:
        self.task_service = task_service

    def attach_society(self, society) -> None:
        self.society = society

    # --- Membership ---

    async def get_member(self, guild_id: str, user_id: str) -> Member:
        member = await self.repo.get_member(guild_id, user_id)
        return member or Member(guild_id=guild_id, user_id=user_id)

    async def is_citizen(self, guild_id: str, user_id: str) -> bool:
        member = await self.repo.get_member(guild_id, user_id)
        return bool(member and member.status == CITIZEN)

    async def on_join(self, guild_id: str, user_id: str) -> Optional[Member]:
        existing = await self.repo.get_member(guild_id, user_id)
        if existing:
            return existing
        if self.bank:
            try:
                await self.bank.ensure_account(guild_id, user_id)
            except Exception as e:
                logger.warning("Could not provision wallet for %s: %s", user_id, e)
        member = Member(guild_id=guild_id, user_id=user_id, status=CATIZEN, joined_at=utcnow())
        await self.repo.register(member)
        task = await self._assign_intro_task(guild_id, user_id)
        if task:
            member.intro_task_id = task.task_id
            await self.repo.set_intro_task(guild_id, user_id, task.task_id)
        return member

    async def _assign_intro_task(self, guild_id: str, user_id: str):
        if not self.task_service:
            return None
        due = datetime.now(timezone.utc) + timedelta(days=INTRO_TASK_DUE_DAYS)
        dto = CreateTaskDTO(
            guild_id=guild_id,
            description=INTRO_TASK_DESCRIPTION,
            assigned_to=user_id,
            due_date=due,
        )
        return await self.task_service.create_task(dto)

    async def complete_intro(self, guild_id: str, user_id: str) -> Optional[str]:
        member = await self.repo.get_member(guild_id, user_id)
        if not member or member.intro_done or not member.intro_task_id:
            return None
        if not self.task_service:
            return None
        await self.task_service.complete_task(member.intro_task_id)
        await self.repo.mark_intro_done(guild_id, user_id)
        return member.intro_task_id

    async def sign(self, guild_id: str, user_id: str) -> Member:
        now = utcnow()
        member = await self.repo.get_member(guild_id, user_id)
        if member and member.status == CITIZEN:
            return member
        if not member:
            member = Member(guild_id=guild_id, user_id=user_id, status=CITIZEN, joined_at=now, signed_at=now)
            await self.repo.register(member)
            if self.bank:
                try:
                    await self.bank.ensure_account(guild_id, user_id)
                except Exception:
                    pass
            return member
        await self.repo.sign(guild_id, user_id, now)
        member.status = CITIZEN
        member.signed_at = now
        return member

    async def enroll_existing(self, guild_id: str, user_ids, as_citizen: bool) -> int:
        enrolled = 0
        for user_id in user_ids:
            if await self.repo.get_member(guild_id, user_id):
                continue
            if self.bank:
                try:
                    await self.bank.ensure_account(guild_id, user_id)
                except Exception:
                    pass
            now = utcnow()
            if as_citizen:
                await self.repo.register(
                    Member(guild_id=guild_id, user_id=user_id, status=CITIZEN, joined_at=now, signed_at=now)
                )
            else:
                await self.repo.register(
                    Member(guild_id=guild_id, user_id=user_id, status=CATIZEN, joined_at=now)
                )
                task = await self._assign_intro_task(guild_id, user_id)
                if task:
                    await self.repo.set_intro_task(guild_id, user_id, task.task_id)
            enrolled += 1
        return enrolled

    async def list_laws(self, guild_id: str):
        if not self.society:
            return []
        try:
            return await self.society.list_laws(guild_id)
        except Exception:
            return []

    # --- Tribunal ---

    async def file_case(self, guild_id: str, accuser_id: str, accused_id: str, law_id: str, evidence: str) -> Case:
        if accuser_id == accused_id:
            raise ValidationError("You cannot accuse yourself.")
        if not await self.is_citizen(guild_id, accuser_id):
            raise ValidationError("Only citizens may bring charges - sign the constitution with `/join` first.")
        if not self.society:
            raise ValidationError("The court is not available.")
        law = await self.society.get_law(law_id)
        if not law:
            raise ValidationError(f"No law `{law_id}` is on the books.")
        if await self.repo.has_open_case_for(guild_id, accused_id):
            raise ValidationError("That comrade already stands accused in an open case.")
        now = utcnow()
        case = Case(
            case_id=f"CASE-{uuid.uuid4().hex[:6].upper()}",
            guild_id=guild_id,
            accuser_id=accuser_id,
            accused_id=accused_id,
            law_id=law_id,
            evidence=evidence,
            created_at=now,
            opened_at=now,
        )
        await self.repo.save_case(case)
        return case

    async def get_case(self, case_id: str) -> Optional[Case]:
        return await self.repo.get_case(case_id)

    async def get_case_by_message(self, message_id: str) -> Optional[Case]:
        return await self.repo.get_case_by_message(message_id)

    async def list_open_cases(self, guild_id: str):
        return await self.repo.list_open_cases(guild_id)

    async def court_vote(self, guild_id: str, case_id: str, voter_id: str, decision: str) -> Case:
        case = await self.repo.get_case(case_id)
        if not case:
            raise ValidationError("No such case.")
        if case.status != CASE_OPEN:
            raise ValidationError("That case is already closed.")
        if voter_id in (case.accuser_id, case.accused_id):
            raise ValidationError("The accuser and the accused do not judge their own case.")
        if not await self.is_citizen(guild_id, voter_id):
            raise ValidationError("Only citizens sit on the jury - sign the constitution with `/join`.")
        decision = decision.lower().strip()
        if decision not in ("guilty", "innocent"):
            raise ValidationError("Vote `guilty` or `innocent`.")
        guilty = [u for u in case.guilty() if u != voter_id]
        innocent = [u for u in case.innocent() if u != voter_id]
        (guilty if decision == "guilty" else innocent).append(voter_id)
        case.guilty_votes = ",".join(guilty)
        case.innocent_votes = ",".join(innocent)
        await self.repo.save_case(case)
        return case

    async def court_defend(self, guild_id: str, case_id: str, user_id: str, text: str) -> Case:
        case = await self.repo.get_case(case_id)
        if not case:
            raise ValidationError("No such case.")
        if user_id != case.accused_id:
            raise ValidationError("Only the accused may enter a defense.")
        if case.status != CASE_OPEN:
            raise ValidationError("That case is already closed.")
        case.defense = text
        await self.repo.save_case(case)
        return case

    async def court_evidence(self, guild_id: str, case_id: str, user_id: str, text: str) -> Case:
        case = await self.repo.get_case(case_id)
        if not case:
            raise ValidationError("No such case.")
        if user_id != case.accuser_id:
            raise ValidationError("Only the accuser may add evidence.")
        if case.status != CASE_OPEN:
            raise ValidationError("That case is already closed.")
        case.evidence = (case.evidence + "\n---\n" + text) if case.evidence else text
        await self.repo.save_case(case)
        return case

    def _verdict(self, case: Case) -> str:
        g, i = len(case.guilty()), len(case.innocent())
        if g + i < COURT_QUORUM:
            return CASE_LAPSED
        return CASE_CONVICTED if g > i else CASE_ACQUITTED

    async def close_case(self, guild_id: str, case_id: str) -> dict:
        case = await self.repo.get_case(case_id)
        if not case:
            raise ValidationError("No such case.")
        if case.status != CASE_OPEN:
            raise ValidationError("That case is already closed.")
        verdict = self._verdict(case)
        case.status = verdict
        case.resolved_at = utcnow()
        await self.repo.save_case(case)
        result = {"case": case, "verdict": verdict, "false_witness": False, "sentence": None}
        if verdict == CASE_ACQUITTED:
            await self._false_witness(case)
            result["false_witness"] = True
        elif verdict == CASE_CONVICTED and case.round >= 2:
            result["sentence"] = await self.execute_sentence(guild_id, case_id)
        return result

    async def appeal_case(self, guild_id: str, case_id: str, user_id: str) -> Case:
        case = await self.repo.get_case(case_id)
        if not case:
            raise ValidationError("No such case.")
        if user_id != case.accused_id:
            raise ValidationError("Only the convicted may appeal.")
        if case.status != CASE_CONVICTED or case.round >= 2:
            raise ValidationError("There is no verdict left to appeal.")
        if case.sentenced:
            raise ValidationError("The sentence has already been carried out.")
        age = _age_hours(case.resolved_at)
        if age is not None and age > COURT_APPEAL_WINDOW_HOURS:
            raise ValidationError("The appeal window has closed.")
        case.round = 2
        case.status = CASE_OPEN
        case.guilty_votes = ""
        case.innocent_votes = ""
        case.opened_at = utcnow()
        case.resolved_at = None
        await self.repo.save_case(case)
        return case

    async def _false_witness(self, case: Case) -> None:
        if not self.bank:
            return
        try:
            bal = await self.bank.balance(case.guild_id, case.accuser_id)
            amount = min(COURT_FALSE_WITNESS_FINE, bal)
            if amount > 0:
                await self.bank.burn(case.guild_id, case.accuser_id, amount, f"false witness {case.case_id}")
        except Exception as e:
            logger.warning("False-witness fine failed for %s: %s", case.case_id, e)

    async def execute_sentence(self, guild_id: str, case_id: str) -> Optional[dict]:
        case = await self.repo.get_case(case_id)
        if not case or case.sentenced or case.status != CASE_CONVICTED:
            return None
        law = await self.society.get_law(case.law_id) if self.society else None
        base_fine = law.fine_amount if law else 0
        prior = await self.repo.count_prior_convictions(guild_id, case.accused_id, case.law_id, case.case_id)
        multiplier = prior + 1
        fine = base_fine * multiplier
        burned, shamed = 0, False
        if fine > 0 and self.bank:
            try:
                bal = await self.bank.balance(guild_id, case.accused_id)
                if bal >= fine:
                    await self.bank.burn(guild_id, case.accused_id, fine, f"court sentence {case.case_id}")
                    burned = fine
                else:
                    if bal > 0:
                        await self.bank.burn(guild_id, case.accused_id, bal, f"court sentence (partial) {case.case_id}")
                        burned = bal
                    shamed = True
            except Exception as e:
                logger.warning("Sentence burn failed for %s: %s", case.case_id, e)
        elif fine > 0:
            shamed = True
        case.sentenced = True
        await self.repo.save_case(case)
        return {
            "case": case,
            "fine": fine,
            "burned": burned,
            "shamed": shamed,
            "multiplier": multiplier,
            "law_title": law.title if law else case.law_id,
        }

    async def sweep_court(self, guild_id: str) -> dict:
        closed, sentenced = [], []
        for case in await self.repo.list_open_cases(guild_id):
            age = _age_hours(case.opened_at)
            if age is not None and age > COURT_VOTE_WINDOW_HOURS:
                try:
                    closed.append(await self.close_case(guild_id, case.case_id))
                except Exception as e:
                    logger.warning("Auto-close failed for %s: %s", case.case_id, e)
        for case in await self.repo.list_convicted_unsentenced(guild_id):
            age = _age_hours(case.resolved_at)
            if age is not None and age > COURT_APPEAL_WINDOW_HOURS:
                try:
                    res = await self.execute_sentence(guild_id, case.case_id)
                    if res:
                        sentenced.append(res)
                except Exception as e:
                    logger.warning("Auto-sentence failed for %s: %s", case.case_id, e)
        return {"closed": closed, "sentenced": sentenced}