"""
tr2.py - Parser + byte-exact rebuilder/editor for And-Kensaku (アンド検索, Wii)
.tr2 word-data files.  LITTLE-ENDIAN throughout.

Format (verified against Misc/Phrase/Puzzle/Double00-02 .tr2):
  FILE HEADER 0x40 bytes: magic ".tr2"; u16 version@0x06; char[32] name@0x08;
    u32 sectionTableOffset@0x38; u32 sectionCount@0x3c
  SECTION TABLE: count * 20 bytes: u32 index, dataOffset(abs), headerSize(0x14),
    size, size2(=size)
  SECTION block: 0x80-byte header (name@0, "jajp"@0x30, "yobi8"@0x38,
    elemType@0x40, u32 entryCount@0x7c), then index = entryCount * 12 bytes
    (u32 id, u32 valueOffset[section-relative], u32 valueLength), then value
    pool.  Strings: value bytes + 1 NUL separator (length EXCLUDES the NUL).
    Scalars: packed at exactly the type width (no separator).
  Element types: UTF-8, UTF-16LE, INT8/16/32, UINT8/16/32, FLOAT (and one
    stray "INT" in Phrase/Puzzle, treated as INT32).

Design for safe editing: each section keeps its ORIGINAL raw bytes. build()
re-emits unmodified sections verbatim (guaranteeing byte-exact round-trip) and
only re-serializes sections you actually edit (sec.dirty=True), recomputing the
index/value-pool/offsets for those.
"""
import struct, sys

def _u16(d,o): return struct.unpack_from('<H',d,o)[0]
def _u32(d,o): return struct.unpack_from('<I',d,o)[0]

_SCALAR = {'INT8':(1,'<b'),'UINT8':(1,'<B'),'INT16':(2,'<h'),'UINT16':(2,'<H'),
           'INT32':(4,'<i'),'UINT32':(4,'<I'),'FLOAT':(4,'<f'),'INT':(4,'<i')}

class Section:
    def __init__(self, name, etype):
        self.name=name; self.etype=etype
        self.entries=[]            # list of [id, value]  (value: str or number)
        self._raw_header=None      # 0x80 bytes, preserved
        self._raw_body=None        # original index+pool bytes, preserved
        self.dirty=False           # set True after you modify .entries
    def is_str(self): return self.etype.startswith('UTF')
    def set_value(self, rid, value):
        for e in self.entries:
            if e[0]==rid: e[1]=value; self.dirty=True; return
        self.entries.append([rid,value]); self.entries.sort(key=lambda e:e[0]); self.dirty=True
    def delete(self, rid):
        self.entries=[e for e in self.entries if e[0]!=rid]; self.dirty=True

class Tr2:
    def __init__(self, path=None, data=None):
        if data is None: data=open(path,'rb').read()
        self.path=path; self.d=data
        assert self.d[:4]==b'.tr2','bad magic'
        self.version=_u16(self.d,6)
        self.name=self.d[8:40].split(b'\0')[0].decode('ascii','replace')
        self._sec_off=_u32(self.d,0x38); self._sec_count=_u32(self.d,0x3c)
        self._file_header=self.d[:0x40]
        self.sections=[]; self._sec_meta=[]
        self._parse()

    def _parse(self):
        d=self.d; o=self._sec_off
        for _ in range(self._sec_count):
            self._sec_meta.append((_u32(d,o),_u32(d,o+4),_u32(d,o+8),_u32(d,o+12),_u32(d,o+16))); o+=20
        for (idx,off,hsz,size,size2) in self._sec_meta:
            name=d[off:off+32].split(b'\0')[0].decode('ascii','replace')
            et=d[off+0x40:off+0x50].split(b'\0')[0].decode('ascii','replace')
            sec=Section(name,et)
            sec._raw_header=d[off:off+0x80]
            sec._raw_body=d[off+0x80:off+size]
            count=_u32(d,off+0x7c); p=off+0x80
            for i in range(count):
                rid=_u32(d,p); voff=_u32(d,p+4); vlen=_u32(d,p+8); p+=12
                vp=off+voff
                if et=='UTF-8': val=d[vp:vp+vlen].decode('utf-8','replace')
                elif et=='UTF-16LE': val=d[vp:vp+vlen].decode('utf-16-le','replace')
                else:
                    w,fmt=_SCALAR.get(et,(4,'<i')); val=struct.unpack_from(fmt,d,vp)[0]
                sec.entries.append([rid,val])
            self.sections.append(sec)

    def get(self,name):
        for s in self.sections:
            if s.name==name: return s
        raise KeyError(name)
    def read(self,name): return {rid:val for rid,val in self.get(name).entries}

    # ---- rebuild ----
    def _section_bytes(self, sec):
        if not sec.dirty and sec._raw_body is not None:
            return bytes(sec._raw_header)+bytes(sec._raw_body)   # verbatim
        # re-serialize edited section
        et=sec.etype; n=len(sec.entries)
        header=bytearray(sec._raw_header); struct.pack_into('<I',header,0x7c,n)
        sec.entries.sort(key=lambda e:e[0])
        index=bytearray(); pool=bytearray(); pool_base=0x80+12*n
        for (rid,val) in sec.entries:
            voff=pool_base+len(pool)
            if et=='UTF-8':
                b=val.encode('utf-8'); vlen=len(b); pool+=b+b'\x00'
            elif et=='UTF-16LE':
                b=val.encode('utf-16-le'); vlen=len(b); pool+=b+b'\x00'
            else:
                w,fmt=_SCALAR.get(et,(4,'<i')); b=struct.pack(fmt,val); vlen=w; pool+=b
            index+=struct.pack('<III',rid,voff,vlen)
        return bytes(header)+bytes(index)+bytes(pool)

    def build(self):
        out=bytearray(self._file_header)
        sec_table_off=self._sec_off
        if len(out)<sec_table_off: out+=b'\x00'*(sec_table_off-len(out))
        table_pos=len(out); out+=b'\x00'*(20*len(self.sections))
        meta=[]
        for si,sec in enumerate(self.sections):
            target=self._sec_meta[si][1]           # original dataOffset
            # Only honor original offset if nothing earlier grew. Pad to it when possible.
            if len(out)<target: out+=b'\x00'*(target-len(out))
            sec_off=len(out)
            block=self._section_bytes(sec); out+=block
            meta.append((self._sec_meta[si][0],sec_off,0x14,len(block),len(block)))
        tp=table_pos
        for (idx,off,hsz,size,size2) in meta:
            struct.pack_into('<IIIII',out,tp,idx,off,hsz,size,size2); tp+=20
        # pad to original length if we ended short and nothing was edited bigger
        if self.path:
            orig_len=len(self.d)
            if len(out)<orig_len: out+=b'\x00'*(orig_len-len(out))
        return bytes(out)

    def save(self,path): open(path,'wb').write(self.build())
    def summary(self):
        print(f'== {self.path} name={self.name!r} sections={len(self.sections)} ==')
        for s in self.sections: print(f'  {s.name:34s} {s.etype:9s} entries={len(s.entries)}')

def load_words(path='Misc.tr2'):
    t=Tr2(path); words=t.read('WordList'); yomi=t.read('YOMI')
    hits=t.read('SINGLEHITS'); rank=t.read('WORD_RANK')
    RANK={0:'S',1:'A',2:'B',3:'C',4:'D',5:'E'}
    return [dict(id=k,term=words[k],yomi=yomi.get(k,''),single_hits=hits.get(k),
                 rank=RANK.get(rank.get(k),rank.get(k))) for k in sorted(words)]

def TR2(path):
    return Tr2(path)