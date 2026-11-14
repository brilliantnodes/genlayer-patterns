# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
MeterConsumerExample: the smallest useful consumer of MeterReader.

It shows how another Intelligent Contract relies on a MeterReader reading
without reading any web page itself: it calls MeterReader's public views
with gl.get_contract_at(...).view() and records what it got.

A real consumer (an escrow, a usage-based payment) would apply the same
pattern and then move money by the returned share. This example only
records, so it can run with test GEN on Studio and be inspected.
"""

import json
from dataclasses import dataclass
from genlayer import *


@allow_storage
@dataclass
class Record:
    id: str
    reading_id: str
    meter_id: str
    window_start: u256
    slots: u256
    kind: str
    target_per_slot: str
    share_bp: u256
    rule: str


class MeterConsumerExample(gl.Contract):
    reader: Address
    records: TreeMap[str, Record]
    count: u256

    def __init__(self, reader_address: str):
        self.reader = Address(reader_address)
        self.count = u256(0)

    @gl.public.write
    def record_share(self, reading_id: str, target_per_slot: str) -> dict:
        """Read one reading and its capped share from MeterReader and store
        both. MeterReader refuses a share for a NO_READING, and that refusal
        stops this call too."""
        reader = gl.get_contract_at(self.reader).view()
        reading = reader.get_reading(reading_id)
        share = reader.delivery_share_bp(reading_id, target_per_slot)
        new_id = str(int(self.count) + 1)
        rec = Record(
            id=new_id,
            reading_id=str(reading["id"]),
            meter_id=str(reading["meter_id"]),
            window_start=u256(int(reading["window_start"])),
            slots=u256(int(reading["slots"])),
            kind=str(reading["kind"]),
            target_per_slot=str(share["target_per_slot"]),
            share_bp=u256(int(share["share_bp"])),
            rule=str(share["rule"]),
        )
        self.records[new_id] = rec
        self.count = u256(int(self.count) + 1)
        return self._view(rec)

    def _view(self, r: Record) -> dict:
        return {
            "id": r.id,
            "reader": self.reader.as_hex,
            "reading_id": r.reading_id,
            "meter_id": r.meter_id,
            "window_start": int(r.window_start),
            "slots": int(r.slots),
            "kind": r.kind,
            "target_per_slot": r.target_per_slot,
            "share_bp": int(r.share_bp),
            "rule": r.rule,
        }

    @gl.public.view
    def get_record(self, record_id: str) -> dict:
        if record_id not in self.records:
            raise gl.vm.UserError("no such record")
        return self._view(self.records[record_id])

    @gl.public.view
    def get_count(self) -> int:
        return int(self.count)

    @gl.public.view
    def get_reader(self) -> str:
        return self.reader.as_hex
