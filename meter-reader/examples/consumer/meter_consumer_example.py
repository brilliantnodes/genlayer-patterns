# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
MeterConsumerExample: the smallest useful consumer of MeterReader.

It shows how another Intelligent Contract relies on MeterReader without
reading any web page itself, the way an escrow or a usage-based payment
would:

  1. create_job pins everything in advance, before the window starts:
     the meter, the exact window and the target per slot. The meter must
     exist, and its specification (page, series, column, resolution, read
     period) is copied into the job, so it is on record what was agreed.
  2. settle_job takes the share from MeterReader's OFFICIAL reading of that
     window (window_share_bp), never a reading id chosen by the caller.
     MeterReader makes the first conclusive reading taken in the meter's
     read period the window's only answer, so settling twice gives the same
     result.
  3. expire_job closes a job whose read period ended (plus a 30-minute
     margin, so a read sent just before the close has been decided) with no
     conclusive reading. A real consumer applies its own default there (for
     example a refund), so funds are never locked for good.

This example records the share instead of moving money, so it can run with
test GEN on Studio and be inspected. A real consumer would pay by it.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from genlayer import *

BP = 10000
MAX_SLOTS = 96
EXPIRY_MARGIN_SECS = 30 * 60  # after the read period, so a read sent just before its close has been decided


def _to_unix(iso: str) -> int:
    return int(datetime.fromisoformat(str(iso).strip().replace("Z", "+00:00")).timestamp())


@allow_storage
@dataclass
class Job:
    id: str
    meter_id: str
    window_start: u256
    slots: u256
    target_per_slot: str
    meter_spec_json: str  # the meter as it was when the job was created
    state: str  # OPEN, SETTLED or EXPIRED
    read_opens: u256
    read_closes: u256
    reading_id: str
    share_bp: u256
    rule: str


class MeterConsumerExample(gl.Contract):
    reader: Address
    jobs: TreeMap[str, Job]
    count: u256

    def __init__(self, reader_address: str):
        self.reader = Address(reader_address)
        self.count = u256(0)

    @gl.public.write
    def create_job(self, meter_id: str, window_start: int, slots: int, target_per_slot: str) -> dict:
        """Pin a meter, a window and a target. Nothing here can be changed later."""
        reader = gl.get_contract_at(self.reader).view()
        meter = reader.get_meter(str(meter_id))  # refuses an unknown meter
        t = str(target_per_slot).strip()
        if t == "" or len(t) > 31 or any(c not in "0123456789" for c in t) or int(t) <= 0:
            raise gl.vm.UserError("target_per_slot must be a positive whole number in the meter's base unit")
        if int(t) % int(meter.get("resolution", 1)) != 0:
            raise gl.vm.UserError("target_per_slot must be a whole multiple of the meter's resolution")
        start, n = int(window_start), int(slots)
        slot = int(meter["slot_minutes"]) * 60
        if n < 1 or n > MAX_SLOTS or start <= 0 or start % slot != 0:
            raise gl.vm.UserError("bad window: 1 to 96 slots, starting on the meter's slot grid")
        opens = start + n * slot + slot + int(meter.get("publish_lag_minutes", 0)) * 60
        closes = opens + int(meter.get("read_within_minutes", 60)) * 60
        if _to_unix(gl.message_raw["datetime"]) >= start:
            raise gl.vm.UserError("a job must be created before its window starts")
        new_id = str(int(self.count) + 1)
        job = Job(
            id=new_id,
            meter_id=str(meter_id),
            window_start=u256(int(window_start)),
            slots=u256(int(slots)),
            target_per_slot=t,
            meter_spec_json=json.dumps(meter, sort_keys=True),
            state="OPEN",
            read_opens=u256(opens),
            read_closes=u256(closes),
            reading_id="",
            share_bp=u256(0),
            rule="",
        )
        self.jobs[new_id] = job
        self.count = u256(int(self.count) + 1)
        return self._view(job)

    @gl.public.write
    def settle_job(self, job_id: str) -> dict:
        """Record the share from the window's official reading. MeterReader
        refuses while the window has no conclusive reading, and that refusal
        stops this call too, so the job simply stays open."""
        if job_id not in self.jobs:
            raise gl.vm.UserError("no such job")
        job = self.jobs[job_id]
        if job.state != "OPEN":
            return self._view(job)  # one answer: settling again changes nothing
        reader = gl.get_contract_at(self.reader).view()
        share = reader.window_share_bp(job.meter_id, int(job.window_start), int(job.slots), job.target_per_slot)
        bp = int(share["share_bp"])
        if bp < 0 or bp > BP:
            raise gl.vm.UserError("share out of range")
        job.state = "SETTLED"
        job.reading_id = str(share["reading_id"])
        job.share_bp = u256(bp)
        job.rule = str(share["rule"])
        return self._view(job)

    @gl.public.write
    def expire_job(self, job_id: str) -> dict:
        """After the meter's read period with no conclusive reading, close the
        job. A real consumer would apply its default here (for example a refund)."""
        if job_id not in self.jobs:
            raise gl.vm.UserError("no such job")
        job = self.jobs[job_id]
        if job.state != "OPEN":
            return self._view(job)
        if _to_unix(gl.message_raw["datetime"]) < int(job.read_closes) + EXPIRY_MARGIN_SECS:
            raise gl.vm.UserError("expiry opens 30 minutes after the read period closes")
        reader = gl.get_contract_at(self.reader).view()
        if reader.get_window_readings(job.meter_id, int(job.window_start), int(job.slots))["official_id"]:
            raise gl.vm.UserError("the window has an official reading: use settle_job")
        job.state = "EXPIRED"
        return self._view(job)

    def _view(self, j: Job) -> dict:
        return {
            "id": j.id,
            "reader": self.reader.as_hex,
            "meter_id": j.meter_id,
            "window_start": int(j.window_start),
            "slots": int(j.slots),
            "target_per_slot": j.target_per_slot,
            "meter": json.loads(j.meter_spec_json),
            "state": j.state,
            "read_opens": int(j.read_opens),
            "read_closes": int(j.read_closes),
            "reading_id": j.reading_id,
            "share_bp": int(j.share_bp),
            "rule": j.rule,
        }

    @gl.public.view
    def get_job(self, job_id: str) -> dict:
        if job_id not in self.jobs:
            raise gl.vm.UserError("no such job")
        return self._view(self.jobs[job_id])

    @gl.public.view
    def get_count(self) -> int:
        return int(self.count)

    @gl.public.view
    def get_reader(self) -> str:
        return self.reader.as_hex
