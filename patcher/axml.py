"""Minimal reader/writer for Android binary XML (AndroidManifest.xml inside an APK).

Only what the patcher needs: parse into a list of chunks/nodes, add strings,
insert elements, and serialize back. No resources.arsc involvement.
"""
import struct

RES_STRING_POOL = 0x0001
RES_XML = 0x0003
RES_XML_START_NS = 0x0100
RES_XML_END_NS = 0x0101
RES_XML_START_ELEMENT = 0x0102
RES_XML_END_ELEMENT = 0x0103
RES_XML_CDATA = 0x0104
RES_XML_RESOURCE_MAP = 0x0180

TYPE_REFERENCE = 0x01
TYPE_STRING = 0x03
TYPE_INT_DEC = 0x10
TYPE_INT_HEX = 0x11
TYPE_INT_BOOLEAN = 0x12

ANDROID_NS = "http://schemas.android.com/apk/res/android"
NO_INDEX = 0xFFFFFFFF


def _uleb_len8(b, o):
    n = b[o]
    if n & 0x80:
        return ((n & 0x7F) << 8) | b[o + 1], o + 2
    return n, o + 1


def _len16(b, o):
    n = struct.unpack_from("<H", b, o)[0]
    if n & 0x8000:
        n2 = struct.unpack_from("<H", b, o + 2)[0]
        return ((n & 0x7FFF) << 16) | n2, o + 4
    return n, o + 2


class StringPool:
    def __init__(self, data):
        typ, hsize, size, count, style_count, flags, str_start, style_start = struct.unpack_from("<HHIIIIII", data, 0)
        assert typ == RES_STRING_POOL
        if style_count:
            raise ValueError("styled strings in manifest are not supported")
        self.utf8 = bool(flags & 0x100)
        self.flags = flags
        offs = struct.unpack_from("<%dI" % count, data, hsize)
        self.strings = []
        for off in offs:
            o = str_start + off
            if self.utf8:
                _, o = _uleb_len8(data, o)       # utf-16 length
                n, o = _uleb_len8(data, o)       # utf-8 byte length
                self.strings.append(data[o:o + n].decode("utf-8"))
            else:
                n, o = _len16(data, o)
                self.strings.append(data[o:o + 2 * n].decode("utf-16-le"))

    def index(self, s, add=True):
        try:
            return self.strings.index(s)
        except ValueError:
            if not add:
                raise
            self.strings.append(s)
            return len(self.strings) - 1

    def serialize(self):
        body = bytearray()
        offs = []
        for s in self.strings:
            offs.append(len(body))
            if self.utf8:
                enc = s.encode("utf-8")
                for n in (len(s.encode("utf-16-le")) // 2, len(enc)):
                    if n > 0x7F:
                        body += bytes([0x80 | (n >> 8), n & 0xFF])
                    else:
                        body.append(n)
                body += enc + b"\0"
            else:
                enc = s.encode("utf-16-le")
                n = len(enc) // 2
                if n > 0x7FFF:
                    body += struct.pack("<HH", 0x8000 | (n >> 16), n & 0xFFFF)
                else:
                    body += struct.pack("<H", n)
                body += enc + b"\0\0"
        while len(body) % 4:
            body.append(0)
        hsize = 28
        str_start = hsize + 4 * len(offs)
        size = str_start + len(body)
        head = struct.pack("<HHIIIIII", RES_STRING_POOL, hsize, size, len(self.strings), 0,
                           self.flags & ~0x1, str_start, 0)  # not sorted any more
        return head + struct.pack("<%dI" % len(offs), *offs) + bytes(body)


class Attr:
    def __init__(self, ns, name, raw, vtype, data):
        self.ns, self.name, self.raw, self.vtype, self.data = ns, name, raw, vtype, data


class Node:
    """One XML tree chunk (start/end element, namespace, cdata)."""

    def __init__(self, typ, line=0, comment=NO_INDEX, **kw):
        self.typ, self.line, self.comment = typ, line, comment
        self.__dict__.update(kw)


class AXML:
    def __init__(self, data):
        typ, hsize, size = struct.unpack_from("<HHI", data, 0)
        assert typ == RES_XML, "not a binary XML file"
        o = hsize
        self.pool = None
        self.resmap = []
        self.nodes = []
        while o < size:
            ctyp, chsize, csize = struct.unpack_from("<HHI", data, o)
            chunk = data[o:o + csize]
            if ctyp == RES_STRING_POOL:
                self.pool = StringPool(chunk)
            elif ctyp == RES_XML_RESOURCE_MAP:
                self.resmap = list(struct.unpack_from("<%dI" % ((csize - 8) // 4), chunk, 8))
            elif ctyp in (RES_XML_START_NS, RES_XML_END_NS):
                line, comment, prefix, uri = struct.unpack_from("<IIII", chunk, 8)
                self.nodes.append(Node(ctyp, line, comment, prefix=prefix, uri=uri))
            elif ctyp == RES_XML_START_ELEMENT:
                line, comment, ns, name, astart, asize, acount, id_i, cls_i, sty_i = \
                    struct.unpack_from("<IIIIHHHHHH", chunk, 8)
                attrs = []
                for k in range(acount):
                    a_ns, a_name, a_raw, _sz, _r0, vtype, vdata = struct.unpack_from(
                        "<IIIHBBI", chunk, 16 + astart + k * asize)
                    attrs.append(Attr(a_ns, a_name, a_raw, vtype, vdata))
                self.nodes.append(Node(ctyp, line, comment, ns=ns, name=name, attrs=attrs,
                                       id_i=id_i, cls_i=cls_i, sty_i=sty_i))
            elif ctyp == RES_XML_END_ELEMENT:
                line, comment, ns, name = struct.unpack_from("<IIII", chunk, 8)
                self.nodes.append(Node(ctyp, line, comment, ns=ns, name=name))
            elif ctyp == RES_XML_CDATA:
                line, comment, text = struct.unpack_from("<III", chunk, 8)
                self.nodes.append(Node(ctyp, line, comment, text=text, tail=chunk[20:]))
            else:
                raise ValueError("unknown chunk type 0x%x" % ctyp)
            o += csize

    # ---- helpers ----------------------------------------------------------

    def s(self, i):
        return None if i == NO_INDEX else self.pool.strings[i]

    def attr_name_index(self, name, resid):
        """Index of an android: attribute name. Attribute names with a resource id
        must sit inside the resource-map range at the start of the pool."""
        for i, rid in enumerate(self.resmap):
            if rid == resid and self.pool.strings[i] == name:
                return i
        # Insert into the resource-mapped prefix: append to the map and move the
        # string to the end of the mapped range. Shifting indices is invasive, so
        # instead require it to exist already.
        raise KeyError("attribute %s (0x%08x) not in manifest resource map" % (name, resid))

    def find(self, tag):
        """Indices of START_ELEMENT nodes with this tag name."""
        return [i for i, n in enumerate(self.nodes) if n.typ == RES_XML_START_ELEMENT and self.s(n.name) == tag]

    def end_of(self, start):
        """Index of the END_ELEMENT matching nodes[start]."""
        depth = 0
        for i in range(start, len(self.nodes)):
            n = self.nodes[i]
            if n.typ == RES_XML_START_ELEMENT:
                depth += 1
            elif n.typ == RES_XML_END_ELEMENT:
                depth -= 1
                if depth == 0:
                    return i
        raise ValueError("unbalanced XML")

    def element(self, tag, attrs):
        """Build a START_ELEMENT node. attrs: list of (name, resid, kind, value)
        with kind in 'str', 'bool', 'int', 'ref'."""
        ns = self.pool.index(ANDROID_NS, add=False)
        out = []
        for name, resid, kind, value in attrs:
            ni = self.attr_name_index(name, resid)
            if kind == "str":
                si = self.pool.index(value)
                out.append(Attr(ns, ni, si, TYPE_STRING, si))
            elif kind == "bool":
                out.append(Attr(ns, ni, NO_INDEX, TYPE_INT_BOOLEAN, 0xFFFFFFFF if value else 0))
            elif kind == "int":
                out.append(Attr(ns, ni, NO_INDEX, TYPE_INT_DEC, value))
            elif kind == "ref":
                out.append(Attr(ns, ni, NO_INDEX, TYPE_REFERENCE, value))
        # Android requires attributes sorted by resource id.
        out.sort(key=lambda a: self.resmap[a.name] if a.name < len(self.resmap) else 0xFFFFFFFF)
        return Node(RES_XML_START_ELEMENT, ns=NO_INDEX, name=self.pool.index(tag), attrs=out,
                    id_i=0, cls_i=0, sty_i=0)

    def end(self, tag):
        return Node(RES_XML_END_ELEMENT, ns=NO_INDEX, name=self.pool.index(tag))

    # ---- output -----------------------------------------------------------

    def serialize(self):
        chunks = [self.pool.serialize()]
        if self.resmap:
            chunks.append(struct.pack("<HHI", RES_XML_RESOURCE_MAP, 8, 8 + 4 * len(self.resmap))
                          + struct.pack("<%dI" % len(self.resmap), *self.resmap))
        for n in self.nodes:
            if n.typ in (RES_XML_START_NS, RES_XML_END_NS):
                chunks.append(struct.pack("<HHIIIII", n.typ, 16, 24, n.line, n.comment, n.prefix, n.uri))
            elif n.typ == RES_XML_START_ELEMENT:
                body = struct.pack("<IIHHHHHH", n.ns, n.name, 20, 20, len(n.attrs), n.id_i, n.cls_i, n.sty_i)
                for a in n.attrs:
                    body += struct.pack("<IIIHBBI", a.ns, a.name, a.raw, 8, 0, a.vtype, a.data)
                chunks.append(struct.pack("<HHIII", n.typ, 16, 16 + len(body), n.line, n.comment) + body)
            elif n.typ == RES_XML_END_ELEMENT:
                chunks.append(struct.pack("<HHIIIII", n.typ, 16, 24, n.line, n.comment, n.ns, n.name))
            elif n.typ == RES_XML_CDATA:
                chunks.append(struct.pack("<HHIIII", n.typ, 16, 28, n.line, n.comment, n.text) + n.tail)
        body = b"".join(chunks)
        return struct.pack("<HHI", RES_XML, 8, 8 + len(body)) + body

    def to_text(self):
        """Readable dump, for diffing and debugging."""
        out, depth = [], 0
        for n in self.nodes:
            if n.typ == RES_XML_START_ELEMENT:
                parts = []
                for a in n.attrs:
                    nm = self.s(a.name)
                    if a.vtype == TYPE_STRING:
                        v = '"%s"' % self.s(a.raw)
                    elif a.vtype == TYPE_INT_BOOLEAN:
                        v = "true" if a.data else "false"
                    elif a.vtype == TYPE_REFERENCE:
                        v = "@0x%08x" % a.data
                    else:
                        v = "0x%x(t%d)" % (a.data, a.vtype)
                    parts.append("%s=%s" % (nm, v))
                out.append("  " * depth + "<%s %s>" % (self.s(n.name), " ".join(parts)))
                depth += 1
            elif n.typ == RES_XML_END_ELEMENT:
                depth -= 1
        return "\n".join(out)


if __name__ == "__main__":
    import sys
    print(AXML(open(sys.argv[1], "rb").read()).to_text())
