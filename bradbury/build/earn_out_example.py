# { "Seq": [{"Depends": "py-genlayer:babwp9t37jw9g4j2bccgn14g6x7x9s1f7dsmh7emvz735pz4zxa0"}] }
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
import genlayer as gl
from genlayer.storage import DynArray, TreeMap, allow as allow_storage
from genlayer.types import *
MAX_ABS = 10 ** 30
BP = 10000
DIGITS = '0123456789'

def _to_unix(iso: str) -> int:
 return int(datetime.fromisoformat(str(iso).strip().replace('Z', '+00:00')).timestamp())

def _int_text(v, label: str) -> int:
 s = str(v).strip() if isinstance(v, (str, int)) and (not isinstance(v, bool)) else ''
 body = s[1:] if s.startswith('-') else s
 if body == '' or any((c not in DIGITS for c in body)) or (len(body) > 1 and body[0] == '0') or (len(body) > 31):
  raise ValueError(f"{label} must be a whole number in the figure's stored units")
 n = int(s)
 if abs(n) > MAX_ABS:
  raise ValueError(f'{label} is too large')
 return n

def _before_end_problem(reading: dict, now: int) -> str:
 end = reading.get('end_ts')
 if isinstance(end, bool) or not isinstance(end, int):
  return 'the reader gave no period end'
 if reading.get('status') != 'NOT_DUE' or now >= end:
  return 'the period has already ended (status ' + str(reading.get('status')) + '): pin a period before it ends'
 if reading.get('has_official') is not False:
  return 'a reading for this period already exists'
 clock = reading.get('clock')
 if isinstance(clock, bool) or not isinstance(clock, int) or clock >= end:
  return 'the reader has already seen a time at or after the period end'
 return ''

def _terms_problem(report: dict, reading: dict, digest: str, period, figure: str, floor_s, target_s, missing_bp, now: int) -> tuple:
 if not isinstance(digest, str) or digest != report.get('digest'):
  return ("the report's digest is not the one pinned", None)
 figs = [f['key'] for f in report['spec']['figures']]
 if figure not in figs:
  return ('the report has no figure ' + str(figure), None)
 if isinstance(period, bool) or not isinstance(period, int) or (not 0 <= period < len(report['spec']['period_ends'])):
  return ('the report has no such period', None)
 if reading.get('digest') != digest or reading.get('period') != period:
  return ('the reader returned another report or period', None)
 p = _before_end_problem(reading, now)
 if p:
  return (p, None)
 try:
  floor, target = (_int_text(floor_s, 'floor'), _int_text(target_s, 'target'))
 except ValueError as e:
  return (str(e), None)
 if target <= floor:
  return ('target must be above floor', None)
 if isinstance(missing_bp, bool) or not isinstance(missing_bp, int) or (not 0 <= missing_bp <= BP):
  return ('missing_seller_bp must be a whole number from 0 to 10000', None)
 return ('', {'floor': floor, 'target': target, 'missing_seller_bp': missing_bp, 'period_end_ts': reading['end_ts']})

def _terms_digest(buyer: str, seller: str, terms: dict) -> str:
 body = {'buyer': buyer.lower(), 'seller': seller.lower(), **terms}
 return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def _seller_share(amount: int, floor: int, target: int, value: int) -> int:
 if value <= floor:
  return 0
 if value >= target:
  return amount
 return amount * (value - floor) // (target - floor)

def _settlement(deal: dict, reading: dict) -> tuple:
 if reading.get('digest') != deal['digest'] or reading.get('period') != deal['period']:
  raise ValueError('the reader returned another report or period')
 st = reading.get('status')
 if st in ('READ', 'MISSING') and reading.get('finalized') is not True:
  raise ValueError("the reader's answer is final but its transaction is not finalized on the network yet: settle again after the finality window")
 if st == 'MISSING':
  s = deal['amount'] * deal['missing_seller_bp'] // BP
  return (s, deal['amount'] - s, f"report missing: {deal['missing_seller_bp']} bp to the seller")
 if st != 'READ':
  if st == 'CLOSING':
   raise ValueError('the reading window has closed but is not settled yet: send tick to the reader, then settle')
  raise ValueError('no final answer yet (status ' + str(st) + ')')
 value = _int_text(reading['figures'][deal['figure']], 'figure')
 s = _seller_share(deal['amount'], deal['floor'], deal['target'], value)
 return (s, deal['amount'] - s, f"{deal['figure']} read as {value}")

@gl.evm.contract_interface
class _Wallet:

 class View:
  pass

 class Write:
  pass

@allow_storage
@dataclass
class Deal:
 id: str
 buyer: str
 seller: str
 terms_json: str
 terms_digest: str
 state: str
 created_at: u256
 result_json: str

class EarnOutExample(gl.contract.Contract):
 reader: Address
 deals: TreeMap[str, Deal]
 count: u256
 locked: u256
 claims: TreeMap[str, u256]
 claims_total: u256

 def __init__(self, reader_address: str):
  self.reader = Address(reader_address)
  self.count = u256(0)
  self.locked = u256(0)
  self.claims_total = u256(0)

 def _now(self) -> int:
  return _to_unix(gl.message.raw['datetime'])

 def _credit(self, to: str, amount: int) -> None:
  if amount > 0:
   k = to.lower()
   self.claims[k] = u256(int(self.claims.get(k) or 0) + amount)
   self.claims_total = u256(int(self.claims_total) + amount)

 def _refuse(self, error: str) -> dict:
  value = int(gl.message.value)
  self._credit(gl.message.sender_address.as_hex, value)
  return {'ok': False, 'error': error, 'refunded': str(value)}

 def _reader_now(self, report_id: str, period: int, now: int) -> tuple:
  reader = gl.contract.get_at(self.reader).view()
  return (reader.get_report(report_id), reader.get_reading(report_id, period, now))

 @gl.public.write.payable
 def create(self, seller: str, report_id: str, digest: str, period: int, figure: str, floor: str, target: str, missing_seller_bp: int) -> dict:
  value = int(gl.message.value)
  buyer = gl.message.sender_address.as_hex
  if value <= 0:
   return self._refuse('send the GEN to escrow with the call')
  try:
   seller_hex = Address(str(seller).strip()).as_hex
  except Exception:
   return self._refuse('seller must be an address')
  if seller_hex.lower() == buyer.lower():
   return self._refuse('seller and buyer must differ')
  if isinstance(period, bool) or not isinstance(period, int):
   return self._refuse('period must be a whole number')
  now = self._now()
  try:
   report, reading = self._reader_now(str(report_id), period, now)
  except Exception:
   return self._refuse('the reader refused: check the report id and period')
  problem, t = _terms_problem(report, reading, digest, period, figure, floor, target, missing_seller_bp, now)
  if problem:
   return self._refuse(problem)
  did = str(int(self.count) + 1)
  terms = {'report_id': str(report_id), 'digest': digest, 'period': period, 'figure': figure, 'floor': t['floor'], 'target': t['target'], 'missing_seller_bp': t['missing_seller_bp'], 'amount': value, 'period_end': reading.get('end'), 'period_end_ts': t['period_end_ts'], 'reading_closes': reading.get('closes')}
  td = _terms_digest(buyer, seller_hex, terms)
  self.deals[did] = Deal(id=did, buyer=buyer, seller=seller_hex, terms_json=json.dumps(terms, sort_keys=True), terms_digest=td, state='OFFERED', created_at=u256(now), result_json='')
  self.count = u256(int(self.count) + 1)
  self.locked = u256(int(self.locked) + value)
  return {'ok': True, 'deal': self.get_deal(did)}

 def _deal(self, deal_id) -> Deal:
  if not isinstance(deal_id, str) or deal_id not in self.deals:
   raise gl.vm.UserError('no such deal')
  return self.deals[deal_id]

 @gl.public.write
 def accept(self, deal_id: str, terms_digest: str) -> dict:
  d = self._deal(deal_id)
  if gl.message.sender_address.as_hex.lower() != d.seller.lower():
   raise gl.vm.UserError('only the seller can accept')
  if d.state != 'OFFERED':
   raise gl.vm.UserError('the deal is ' + d.state + ', not OFFERED')
  if not isinstance(terms_digest, str) or terms_digest != d.terms_digest:
   raise gl.vm.UserError('terms_digest is not the one this deal offers')
  deal = json.loads(d.terms_json)
  now = self._now()
  _, reading = self._reader_now(deal['report_id'], deal['period'], now)
  if reading.get('digest') != deal['digest'] or reading.get('period') != deal['period']:
   raise gl.vm.UserError('the reader returned another report or period')
  p = _before_end_problem(reading, now)
  if p:
   raise gl.vm.UserError(p + ': too late to accept')
  d.state = 'OPEN'
  d.result_json = json.dumps({'accepted_at': now}, sort_keys=True)
  return {'ok': True, 'deal': self.get_deal(deal_id)}

 @gl.public.write
 def cancel(self, deal_id: str) -> dict:
  d = self._deal(deal_id)
  if gl.message.sender_address.as_hex.lower() != d.buyer.lower():
   raise gl.vm.UserError('only the buyer can cancel')
  if d.state != 'OFFERED':
   raise gl.vm.UserError('the deal is ' + d.state + ': only an offer not yet accepted can be cancelled')
  deal = json.loads(d.terms_json)
  self.locked = u256(int(self.locked) - deal['amount'])
  self._credit(d.buyer, deal['amount'])
  d.state = 'CANCELLED'
  d.result_json = json.dumps({'cancelled_at': self._now(), 'to_buyer': deal['amount'], 'to_seller': 0}, sort_keys=True)
  return {'ok': True, 'deal': self.get_deal(deal_id)}

 @gl.public.write
 def settle(self, deal_id: str) -> dict:
  d = self._deal(deal_id)
  if d.state in ('SETTLED', 'CANCELLED', 'EXPIRED'):
   return {'ok': True, 'deal': self.get_deal(deal_id)}
  deal = json.loads(d.terms_json)
  now = self._now()
  if d.state == 'OFFERED':
   if now < deal['period_end_ts']:
    raise gl.vm.UserError('the seller has not accepted yet and the period has not ended')
   self.locked = u256(int(self.locked) - deal['amount'])
   self._credit(d.buyer, deal['amount'])
   d.state = 'EXPIRED'
   d.result_json = json.dumps({'expired_at': now, 'to_buyer': deal['amount'], 'to_seller': 0, 'note': 'not accepted before the period end'}, sort_keys=True)
   return {'ok': True, 'deal': self.get_deal(deal_id)}
  reading = gl.contract.get_at(self.reader).view().get_reading(deal['report_id'], deal['period'], now)
  try:
   to_seller, to_buyer, note = _settlement(deal, reading)
  except (ValueError, KeyError, TypeError) as e:
   raise gl.vm.UserError(str(e))
  if to_seller < 0 or to_buyer < 0 or to_seller + to_buyer != deal['amount']:
   raise gl.vm.UserError('internal: money does not add up')
  self.locked = u256(int(self.locked) - deal['amount'])
  self._credit(d.seller, to_seller)
  self._credit(d.buyer, to_buyer)
  accepted = json.loads(d.result_json).get('accepted_at') if d.result_json else None
  d.state = 'SETTLED'
  d.result_json = json.dumps({'status': reading['status'], 'to_seller': to_seller, 'to_buyer': to_buyer, 'note': note, 'accepted_at': accepted, 'figures': reading.get('figures', {}), 'read_at': reading.get('read_at'), 'settled_at': now}, sort_keys=True)
  return {'ok': True, 'deal': self.get_deal(deal_id)}

 @gl.public.write
 def withdraw(self, amount: int=0) -> dict:
  me = gl.message.sender_address.as_hex
  k = me.lower()
  have = int(self.claims.get(k) or 0)
  if isinstance(amount, bool) or not isinstance(amount, int):
   raise gl.vm.UserError('amount must be a whole number of wei (0 for everything)')
  if have <= 0:
   raise gl.vm.UserError('nothing to withdraw for this address')
  if amount == 0:
   amount = have
  if not 0 < amount <= have:
   raise gl.vm.UserError(f'amount must be 1 to {have} wei (0 for everything)')
  self.claims[k] = u256(have - amount)
  self.claims_total = u256(int(self.claims_total) - amount)
  _Wallet(Address(me)).emit_transfer(value=u256(amount))
  return {'ok': True, 'amount': str(amount), 'left': str(have - amount)}

 @gl.public.view
 def get_deal(self, deal_id: str) -> dict:
  d = self._deal(deal_id)
  t = json.loads(d.terms_json)
  out = {'id': d.id, 'buyer': d.buyer, 'seller': d.seller, 'state': d.state, 'created_at': int(d.created_at), 'terms_digest': d.terms_digest, **{k: str(v) if k in ('floor', 'target', 'amount') else v for k, v in t.items()}}
  if d.result_json:
   r = json.loads(d.result_json)
   for k in ('to_seller', 'to_buyer'):
    if k in r:
     r[k] = str(r[k])
   out['result'] = r
  return out

 @gl.public.view
 def get_claimable(self, address: str) -> str:
  try:
   k = Address(str(address).strip()).as_hex.lower()
  except Exception:
   return '0'
  return str(int(self.claims.get(k) or 0))

 @gl.public.view
 def totals(self) -> dict:
  return {'deals': int(self.count), 'locked': str(int(self.locked)), 'credited': str(int(self.claims_total)), 'reader': self.reader.as_hex}
