# { "Seq": [{"Depends": "py-genlayer:babwp9t37jw9g4j2bccgn14g6x7x9s1f7dsmh7emvz735pz4zxa0"}] }
import json
from dataclasses import dataclass
from datetime import datetime
import genlayer as gl
from genlayer.storage import DynArray, TreeMap, allow as allow_storage
from genlayer.types import *
BP = 10000
MAX_SLOTS = 96
EXPIRY_MARGIN_SECS = 30 * 60

def _to_unix(iso: str) -> int:
 return int(datetime.fromisoformat(str(iso).strip().replace('Z', '+00:00')).timestamp())

@allow_storage
@dataclass
class Job:
 id: str
 meter_id: str
 window_start: u256
 slots: u256
 target_per_slot: str
 meter_spec_json: str
 state: str
 read_opens: u256
 read_closes: u256
 reading_id: str
 share_bp: u256
 rule: str

class MeterConsumerExample(gl.contract.Contract):
 reader: Address
 jobs: TreeMap[str, Job]
 count: u256

 def __init__(self, reader_address: str):
  self.reader = Address(reader_address)
  self.count = u256(0)

 @gl.public.write
 def create_job(self, meter_id: str, window_start: int, slots: int, target_per_slot: str) -> dict:
  reader = gl.contract.get_at(self.reader).view()
  meter = reader.get_meter(str(meter_id))
  t = str(target_per_slot).strip()
  if t == '' or len(t) > 31 or any((c not in '0123456789' for c in t)) or (int(t) <= 0):
   raise gl.vm.UserError("target_per_slot must be a positive whole number in the meter's base unit")
  if int(t) % int(meter.get('resolution', 1)) != 0:
   raise gl.vm.UserError("target_per_slot must be a whole multiple of the meter's resolution")
  start, n = (int(window_start), int(slots))
  slot = int(meter['slot_minutes']) * 60
  if n < 1 or n > MAX_SLOTS or start <= 0 or (start % slot != 0):
   raise gl.vm.UserError("bad window: 1 to 96 slots, starting on the meter's slot grid")
  opens = start + n * slot + slot + int(meter.get('publish_lag_minutes', 0)) * 60
  closes = opens + int(meter.get('read_within_minutes', 60)) * 60
  if _to_unix(gl.message.raw['datetime']) >= start:
   raise gl.vm.UserError('a job must be created before its window starts')
  new_id = str(int(self.count) + 1)
  job = Job(id=new_id, meter_id=str(meter_id), window_start=u256(int(window_start)), slots=u256(int(slots)), target_per_slot=t, meter_spec_json=json.dumps(meter, sort_keys=True), state='OPEN', read_opens=u256(opens), read_closes=u256(closes), reading_id='', share_bp=u256(0), rule='')
  self.jobs[new_id] = job
  self.count = u256(int(self.count) + 1)
  return self._view(job)

 @gl.public.write
 def settle_job(self, job_id: str) -> dict:
  if job_id not in self.jobs:
   raise gl.vm.UserError('no such job')
  job = self.jobs[job_id]
  if job.state != 'OPEN':
   return self._view(job)
  reader = gl.contract.get_at(self.reader).view()
  share = reader.window_share_bp(job.meter_id, int(job.window_start), int(job.slots), job.target_per_slot)
  bp = int(share['share_bp'])
  if bp < 0 or bp > BP:
   raise gl.vm.UserError('share out of range')
  job.state = 'SETTLED'
  job.reading_id = str(share['reading_id'])
  job.share_bp = u256(bp)
  job.rule = str(share['rule'])
  return self._view(job)

 @gl.public.write
 def expire_job(self, job_id: str) -> dict:
  if job_id not in self.jobs:
   raise gl.vm.UserError('no such job')
  job = self.jobs[job_id]
  if job.state != 'OPEN':
   return self._view(job)
  if _to_unix(gl.message.raw['datetime']) < int(job.read_closes) + EXPIRY_MARGIN_SECS:
   raise gl.vm.UserError('expiry opens 30 minutes after the read period closes')
  reader = gl.contract.get_at(self.reader).view()
  if reader.get_window_readings(job.meter_id, int(job.window_start), int(job.slots))['official_id']:
   raise gl.vm.UserError('the window has an official reading: use settle_job')
  job.state = 'EXPIRED'
  return self._view(job)

 def _view(self, j: Job) -> dict:
  return {'id': j.id, 'reader': self.reader.as_hex, 'meter_id': j.meter_id, 'window_start': int(j.window_start), 'slots': int(j.slots), 'target_per_slot': j.target_per_slot, 'meter': json.loads(j.meter_spec_json), 'state': j.state, 'read_opens': int(j.read_opens), 'read_closes': int(j.read_closes), 'reading_id': j.reading_id, 'share_bp': int(j.share_bp), 'rule': j.rule}

 @gl.public.view
 def get_job(self, job_id: str) -> dict:
  if job_id not in self.jobs:
   raise gl.vm.UserError('no such job')
  return self._view(self.jobs[job_id])

 @gl.public.view
 def get_count(self) -> int:
  return int(self.count)

 @gl.public.view
 def get_reader(self) -> str:
  return self.reader.as_hex
