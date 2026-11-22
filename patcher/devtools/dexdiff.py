"""Minimal DEX reader: per-method code hashes + referenced strings/methods/fields.
usage: dexdiff.py A.dex B.dex   -> methods added/removed/changed, with refs
       dexdiff.py A.dex          -> dump all classes/methods with refs
"""
import struct, sys, hashlib

def uleb(b, o):
    r = s = 0
    while True:
        x = b[o]; o += 1
        r |= (x & 0x7f) << s; s += 7
        if x < 0x80: return r, o

# instruction width (16-bit units) by opcode, for walking bytecode
W = [1]*256
def setw(rng, w):
    for i in rng: W[i] = w
setw([0x01,0x04,0x07,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f,0x10,0x11,0x12,0x1d,0x1e,0x21,0x27,0x28], 1)
setw(range(0x7b,0x90), 1); setw(range(0xb0,0xd0), 1)
setw([0x02,0x05,0x08,0x13,0x15,0x16,0x19,0x1a,0x1c,0x1f,0x20,0x22,0x23,0x29], 2)
setw(range(0x2d,0x32), 2); setw(range(0x32,0x3e), 2); setw(range(0x44,0x6e), 2)
setw(range(0x90,0xb0), 2); setw(range(0xd0,0xe3), 2); setw([0xfe,0xff], 2)
setw([0x03,0x06,0x09,0x14,0x17,0x1b,0x24,0x25,0x26,0x2a,0x2b,0x2c], 3)
setw(range(0x6e,0x73), 3); setw(range(0x74,0x79), 3); setw([0xfa], 4); setw([0xfb], 4); setw([0xfc,0xfd], 3)
setw([0x18], 5)

class Dex:
    def __init__(s, path):
        b = s.b = open(path, 'rb').read()
        def hdr(o): return struct.unpack_from('<II', b, o)
        sn, so = hdr(0x38); tn, to = hdr(0x40); fn, fo = hdr(0x50); mn, mo = hdr(0x58); cn, co = hdr(0x60)
        pn, po = hdr(0x48)
        s.str = []
        for i in range(sn):
            off = struct.unpack_from('<I', b, so + 4*i)[0]
            _, o = uleb(b, off); e = b.index(0, o)
            s.str.append(b[o:e].decode('utf-8', 'replace'))
        s.typ = [s.str[struct.unpack_from('<I', b, to + 4*i)[0]] for i in range(tn)]
        s.proto = []
        for i in range(pn):
            _, ret, par = struct.unpack_from('<III', b, po + 12*i)
            ps = []
            if par:
                n = struct.unpack_from('<I', b, par)[0]
                ps = [s.typ[struct.unpack_from('<H', b, par+4+2*k)[0]] for k in range(n)]
            s.proto.append('(' + ''.join(ps) + ')' + s.typ[ret])
        s.fld = []
        for i in range(fn):
            c, t, n = struct.unpack_from('<HHI', b, fo + 8*i)
            s.fld.append(f'{s.typ[c]}->{s.str[n]}:{s.typ[t]}')
        s.meth = []
        for i in range(mn):
            c, p, n = struct.unpack_from('<HHI', b, mo + 8*i)
            s.meth.append(f'{s.typ[c]}->{s.str[n]}{s.proto[p]}')
        s.code = {}  # method sig -> (hash, refs)
        for i in range(cn):
            cls, flags, sup, ifs, src, ann, data, sv = struct.unpack_from('<8I', b, co + 32*i)
            if not data: continue
            o = data
            sf, o = uleb(b, o); inf, o = uleb(b, o); dm, o = uleb(b, o); vm, o = uleb(b, o)
            for _ in range(sf + inf):
                _, o = uleb(b, o); _, o = uleb(b, o)
            idx = 0
            for k in range(dm + vm):
                if k == dm: idx = 0
                d, o = uleb(b, o); idx += d
                _, o = uleb(b, o); coff, o = uleb(b, o)
                sig = s.meth[idx]
                try: s.code[sig] = s.read_code(coff) if coff else ('abstract', [])
                except Exception as e: s.code[sig] = ('err', ['PARSE ERROR %r' % e])
    def read_code(s, off):
        b = s.b
        n_ins = struct.unpack_from('<I', b, off + 12)[0]
        ins = b[off+16: off+16+2*n_ins]
        refs = []; pc = 0
        while pc < n_ins:
            u = struct.unpack_from('<H', ins, 2*pc)[0]; op = u & 0xff
            if op == 0 and u in (0x100, 0x200, 0x300):  # payloads
                if u == 0x100: sz = struct.unpack_from('<H', ins, 2*pc+2)[0]; pc += sz*2 + 4
                elif u == 0x200: sz = struct.unpack_from('<H', ins, 2*pc+2)[0]; pc += sz*4 + 2
                else:
                    ew, sz = struct.unpack_from('<HI', ins, 2*pc+2); pc += (sz*ew + 1)//2 + 4
                continue
            if op == 0x1a: refs.append('"' + s.str[struct.unpack_from('<H', ins, 2*pc+2)[0]] + '"')
            elif op == 0x1b: refs.append('"' + s.str[struct.unpack_from('<I', ins, 2*pc+2)[0]] + '"')
            elif 0x6e <= op <= 0x72 or 0x74 <= op <= 0x78:
                refs.append('call ' + s.meth[struct.unpack_from('<H', ins, 2*pc+2)[0]])
            elif 0x52 <= op <= 0x6d:
                refs.append(('get ' if (op-0x52) % 14 < 7 else 'put ') + s.fld[struct.unpack_from('<H', ins, 2*pc+2)[0]])
            elif op == 0x12: refs.append('const4 %d' % (((u>>12)^8)-8))
            elif op in (0x14, 0x13): refs.append('const %d' % (struct.unpack_from('<i' if op==0x14 else '<h', ins, 2*pc+2)[0]))
            elif op == 0x22 or op == 0x1f or op == 0x20: refs.append(('new ' if op==0x22 else 'type ') + s.typ[struct.unpack_from('<H', ins, 2*pc+2)[0]])
            pc += W[op]
        return hashlib.md5(ins).hexdigest(), refs

def show(sig, refs, pre):
    print(pre, sig)
    for r in refs: print('      ', r)

a = Dex(sys.argv[1])
if len(sys.argv) == 2:
    for sig, (h, refs) in sorted(a.code.items()): show(sig, refs, '*')
    sys.exit()
bb = Dex(sys.argv[2])
for sig in sorted(set(a.code) | set(bb.code)):
    if sig not in a.code: show(sig, bb.code[sig][1], '+ ADDED')
    elif sig not in bb.code: show(sig, a.code[sig][1], '- REMOVED')
    elif a.code[sig][1] != bb.code[sig][1]:
        import difflib
        print('~ CHANGED', sig)
        for l in difflib.unified_diff(a.code[sig][1], bb.code[sig][1], lineterm='', n=2):
            if not l.startswith(('---','+++')): print('      ', l)
