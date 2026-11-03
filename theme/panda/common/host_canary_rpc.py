"""Bounded Host Canary RPC. Transport identity is enforced by native init.

Session/epoch fields detect drift; they are not credentials. Workers have only
one inherited socket, and the custodian authenticates its registered sender
before forwarding any frame. No retries, replay, filesystem paths or cleanup
capabilities are implemented by this module.
"""
import base64
import hashlib
import json
import os
import re
import zlib

MAX_FRAME = 32768
CHUNK = 12288
MAX_MESSAGE = 2 * 1024 * 1024
MAX_PARTS = (MAX_MESSAGE + CHUNK - 1) // CHUNK
MAX_REQUESTS = 4096


class ProtocolError(ValueError):
    pass


def pack(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value: raise ProtocolError('duplicate RPC field')
        value[key] = item
    return value


def unpack(raw):
    if type(raw) is not bytes or not raw or len(raw) > MAX_MESSAGE:
        raise ProtocolError('RPC size/type bound')
    try:
        value = json.loads(raw, object_pairs_hook=_pairs)
        if pack(value) != raw: raise ProtocolError('noncanonical RPC')
        return value
    except (UnicodeError, RecursionError, OverflowError, json.JSONDecodeError) as exc:
        raise ProtocolError('invalid RPC encoding') from exc


def scope(session, epoch):
    if not isinstance(session, str) or not re.fullmatch('[0-9a-f]{32}', session) or type(epoch) is not int or not 1 <= epoch <= MAX_REQUESTS:
        raise ProtocolError('invalid RPC session/epoch')


def pieces(raw):
    if len(raw) > MAX_MESSAGE: raise ProtocolError('RPC message budget exceeded')
    return [raw[n:n + CHUNK] for n in range(0, len(raw), CHUNK)] or [b'']


def frame(session, epoch, seq, kind, **fields):
    raw = pack(dict(v=1, session=session, epoch=epoch, seq=seq, type=kind, **fields))
    if len(raw) > MAX_FRAME: raise ProtocolError('RPC frame exceeded')
    return raw


def request_frames(session, epoch, seq, op, args):
    scope(session, epoch)
    if type(op) is not str or not re.fullmatch('[a-z_]{1,40}', op) or type(args) is not dict:
        raise ProtocolError('invalid RPC operation')
    raw = pack({'op': op, 'args': args})
    parts = pieces(raw)
    digest = hashlib.sha256(raw).hexdigest()
    return [frame(session, epoch, seq, 'request', part=n, total=len(parts), digest=digest,
                  data=base64.b64encode(data).decode('ascii')) for n, data in enumerate(parts)]


def decode_chunk(value):
    if (type(value['part']) is not int or type(value['total']) is not int
            or not 1 <= value['total'] <= MAX_PARTS or not 0 <= value['part'] < value['total']
            or not isinstance(value['digest'], str) or not re.fullmatch('[0-9a-f]{64}', value['digest'])
            or not isinstance(value['data'], str) or len(value['data']) > CHUNK * 4 // 3 + 4):
        raise ProtocolError('invalid RPC fragment')
    try: raw = base64.b64decode(value['data'], validate=True)
    except (ValueError, TypeError) as exc: raise ProtocolError('invalid RPC fragment encoding') from exc
    if len(raw) > CHUNK or base64.b64encode(raw).decode('ascii') != value['data']:
        raise ProtocolError('RPC fragment bound/canonical encoding')
    return raw


class FdIO:
    """Only used inside the separately approved kernel-restricted worker."""
    @staticmethod
    def write(fd, raw): return os.write(fd, raw)
    @staticmethod
    def read(fd, bound): return os.read(fd, bound)


class Client:
    def __init__(self, fd, session, epoch, *, io=None):
        scope(session, epoch)
        if type(fd) is not int or fd < 3: raise ProtocolError('explicit inherited RPC descriptor required')
        self.fd, self.session, self.epoch = fd, session, epoch
        self.io, self.seq, self.failed = io or FdIO(), 1, False

    def exchange(self, raw):
        if self.io.write(self.fd, raw) != len(raw): raise ProtocolError('short RPC send; never retry')
        reply = self.io.read(self.fd, MAX_FRAME + 1)
        if not reply or len(reply) > MAX_FRAME: raise ProtocolError('lost/oversized RPC reply')
        value = unpack(reply)
        if type(value) is not dict: raise ProtocolError('RPC reply object required')
        for key, expected in (('v', 1), ('session', self.session), ('epoch', self.epoch), ('seq', self.seq)):
            if value.get(key) != expected or type(value.get(key)) is not type(expected):
                raise ProtocolError('RPC reply scope/sequence differs')
        return value

    def call(self, op, args):
        if self.failed or self.seq > MAX_REQUESTS: raise ProtocolError('RPC client revoked/budget exhausted')
        try:
            packets = request_frames(self.session, self.epoch, self.seq, op, args)
            reply = None
            for n, packet in enumerate(packets):
                reply = self.exchange(packet)
                if n + 1 < len(packets) and (reply.get('type') != 'continue' or reply.get('part') != n):
                    raise ProtocolError('RPC fragment acknowledgement differs')
            data, digest, total = bytearray(), None, None
            n = 0
            while True:
                if reply.get('type') != 'result' or reply.get('part') != n:
                    raise ProtocolError('RPC result fragment order differs')
                raw = decode_chunk(reply)
                if digest is None: digest, total = reply['digest'], reply['total']
                if (reply['digest'], reply['total']) != (digest, total):
                    raise ProtocolError('RPC result identity differs')
                data.extend(raw)
                if len(data) > MAX_MESSAGE: raise ProtocolError('RPC result budget exceeded')
                n += 1
                if n == total: break
                reply = self.exchange(frame(self.session, self.epoch, self.seq, 'fetch', part=n))
            if hashlib.sha256(data).hexdigest() != digest: raise ProtocolError('RPC result digest differs')
            result = unpack(bytes(data))
            if type(result) is not dict or set(result) not in ({'ok', 'result'}, {'ok', 'error'}):
                raise ProtocolError('invalid RPC result envelope')
            accepted = self.exchange(frame(self.session, self.epoch, self.seq, 'ack', digest=digest))
            if accepted.get('type') != 'accepted': raise ProtocolError('RPC result acknowledgement incomplete')
            self.seq += 1
            if result['ok'] is not True:
                self.failed = True
                error = result['error']
                if error.get('errno') is not None: raise OSError(error['errno'], error['message'])
                raise ProtocolError(error['message'])
            return result['result']
        except BaseException:
            self.failed = True
            raise


class RequestBudget:
    """One continuously held fixture budget; epochs never replenish requests."""
    def __init__(self, store, ledger, session):
        scope(session, 1)
        self.store, self.ledger, self.session = store, ledger, session
        self.epoch, self.active, self.last, self._total = 0, False, 0, 0

    @property
    def total(self):
        return self._total

    def _refuse(self):
        self.store.preserve('cumulative RPC budget/epoch lost')
        raise ProtocolError('cumulative RPC budget/epoch lost')

    def open_epoch(self, epoch):
        if type(epoch) is not int or self.active or epoch != self.epoch + 1:
            self._refuse()
        self.epoch, self.active, self.last = epoch, True, 0

    def reserve(self, epoch, sequence):
        if not self.active or epoch != self.epoch or sequence != self.last + 1 or self._total >= MAX_REQUESTS:
            self._refuse()
        self._total += 1
        self.last = sequence
        return self._total

    def close_epoch(self, epoch):
        if not self.active or epoch != self.epoch:
            self._refuse()
        self.active = False


class Server:
    """One controller-owned store, one native-authenticated worker epoch.

    accept() must only be called after native sender/generation authentication.
    The store owns all custody; JSON, this framer, and successful callbacks cannot
    create a lifecycle or teardown grant.
    """
    def __init__(self, store, ledger, session, epoch, *, budget=None):
        scope(session, epoch)
        if budget is not None and (type(budget) is not RequestBudget or budget.store is not store
                or budget.ledger is not ledger or budget.session != session
                or not budget.active or budget.epoch != epoch):
            raise ProtocolError('original shared request budget required')
        self.budget, self.retired = budget, False
        self.store, self.ledger, self.session, self.epoch = store, ledger, session, epoch
        self.seq, self.parts, self.pending, self.revoked = 1, [], None, False
        self.total = self.digest = None
        self.reply_parts, self.reply_digest, self.next_reply = [], None, 0
        self.failed_result = False
        self.contents = {}

    @property
    def quiescent(self):
        return not self.revoked and not self.parts and self.pending is None and not self.reply_parts

    def abort(self, reason):
        self.revoked = True
        self.store.preserve(reason)

    def retire(self):
        if self.retired or not self.quiescent:
            self.abort('incomplete or duplicate epoch retirement')
            raise ProtocolError('incomplete or duplicate epoch retirement')
        self.retired = True  # retain all content/evidence; late frames poison custody

    def _retain(self, direction, raw):
        # Complete evidence, not replay authority. Compression bounds redundant
        # schema/image bytes; the existing ledger ceilings still fail closed.
        digest = hashlib.sha256(raw).hexdigest()
        if digest in self.contents:
            previous, source_seq, source_direction = self.contents[digest]
            decoder = zlib.decompressobj()
            original = decoder.decompress(previous, MAX_MESSAGE + 1)
            if original != raw or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise ProtocolError('RPC content digest/cache differs')
            self.ledger.append({'kind':'rpc-content-reference','epoch':self.epoch,'seq':self.seq,
                'direction':direction,'sha256':digest,'bytes':len(raw),
                'source_seq':source_seq,'source_direction':source_direction})
            return
        encoded = zlib.compress(raw, 9)
        chunks = [encoded[n:n+1536] for n in range(0,len(encoded),1536)]
        for part, data in enumerate(chunks):
            self.ledger.append({'kind':'rpc-content','epoch':self.epoch,'seq':self.seq,
                'direction':direction,'encoding':'zlib+base64','part':part,'total':len(chunks),
                'sha256':digest,'bytes':len(raw),'data':base64.b64encode(data).decode('ascii')})
        self.contents[digest] = (encoded,self.seq,direction)

    def accept(self, raw):
        if self.retired:
            self.abort('retired worker epoch replay')
            raise ProtocolError('retired worker epoch replay')
        if self.revoked or self.seq > MAX_REQUESTS:
            self.abort('RPC server revoked/budget exhausted')
            raise ProtocolError('RPC server revoked/budget exhausted')
        try:
            if len(raw) > MAX_FRAME: raise ProtocolError('RPC frame budget exceeded')
            value = unpack(raw)
            if type(value) is not dict: raise ProtocolError('RPC object required')
            expected = {'v': 1, 'session': self.session, 'epoch': self.epoch, 'seq': self.seq}
            if any(value.get(k) != v or type(value.get(k)) is not type(v) for k, v in expected.items()):
                raise ProtocolError('RPC scope/sequence differs')
            kind = value.get('type')
            common = {*expected, 'type'}
            if kind == 'request':
                if set(value) != common | {'part', 'total', 'digest', 'data'} or self.pending is not None:
                    raise ProtocolError('unexpected RPC request fields/state')
                data = decode_chunk(value)
                if value['part'] != len(self.parts): raise ProtocolError('RPC fragment duplicate/gap')
                if self.total is None: self.total, self.digest = value['total'], value['digest']
                if (value['total'], value['digest']) != (self.total, self.digest):
                    raise ProtocolError('RPC fragment identity differs')
                self.parts.append(data)
                if sum(map(len, self.parts)) > MAX_MESSAGE: raise ProtocolError('RPC request budget exceeded')
                if len(self.parts) != self.total:
                    return frame(self.session, self.epoch, self.seq, 'continue', part=value['part'])
                request = b''.join(self.parts)
                if hashlib.sha256(request).hexdigest() != self.digest: raise ProtocolError('RPC request digest differs')
                message = unpack(request)
                if type(message) is not dict or set(message) != {'op', 'args'} or type(message['op']) is not str or type(message['args']) is not dict:
                    raise ProtocolError('invalid RPC request envelope')
                self.pending = message
                charge = {} if self.budget is None else {'total_request': self.budget.reserve(self.epoch, self.seq)}
                self._retain('request', request)
                self.ledger.append({'kind': 'rpc-intent', 'epoch': self.epoch, 'seq': self.seq,
                                    'op': message['op'], 'sha256': self.digest, 'bytes': len(request), **charge})
                try:
                    result = {'ok': True, 'result': self.store.dispatch(message['op'], message['args'])}
                except Exception as exc:
                    self.failed_result = True
                    self.store.preserve('broker operation failed')
                    result = {'ok': False, 'error': {'errno': getattr(exc, 'errno', None), 'message': str(exc)[:512]}}
                encoded = pack(result)
                self.reply_parts = pieces(encoded)
                self.reply_digest = hashlib.sha256(encoded).hexdigest()
                self._retain('result', encoded)
                self.ledger.append({'kind': 'rpc-result', 'epoch': self.epoch, 'seq': self.seq,
                                    'ok': result['ok'], 'sha256': self.reply_digest, 'bytes': len(encoded)})
                self.next_reply = 1
                return self._reply(0)
            if kind == 'fetch':
                if set(value) != common | {'part'} or not self.reply_parts or type(value['part']) is not int or value['part'] != self.next_reply:
                    raise ProtocolError('RPC reply fetch duplicate/gap')
                self.next_reply += 1
                return self._reply(value['part'])
            if kind == 'ack':
                if (set(value) != common | {'digest'} or not self.reply_parts or
                        self.next_reply != len(self.reply_parts) or value['digest'] != self.reply_digest):
                    raise ProtocolError('RPC result acknowledgement differs')
                self.ledger.append({'kind': 'rpc-ack', 'epoch': self.epoch, 'seq': self.seq, 'sha256': self.reply_digest})
                reply = frame(self.session, self.epoch, self.seq, 'accepted')
                self.parts, self.pending, self.reply_parts = [], None, []
                self.total = self.digest = self.reply_digest = None
                self.seq += 1
                if self.failed_result: self.abort('broker failure acknowledged; no further grants')
                return reply
            raise ProtocolError('unknown RPC frame type')
        except BaseException:
            self.abort('RPC protocol/durability lost')
            raise

    def _reply(self, part):
        if not 0 <= part < len(self.reply_parts): raise ProtocolError('RPC reply fragment out of bounds')
        return frame(self.session, self.epoch, self.seq, 'result', part=part, total=len(self.reply_parts),
                     digest=self.reply_digest, data=base64.b64encode(self.reply_parts[part]).decode('ascii'))
