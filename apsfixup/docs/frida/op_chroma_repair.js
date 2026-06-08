// op_chroma_repair.js — sm8850 (infiniti) — THE validation probe (it *is* the fix, in JS).
//
// Ported from spkal01's dodge probe. Implements the SAME three corrections that the native
// libapsfixup.so applies, by hooking the two functions BY NAME (no offset hardcode):
//   (1) ARC_Turbo_RAW_Process  (libarcsoft_turbo_raw.so) — repair the garbage chroma plane ptr
//       (+ chroma pitch at the +0x40 plane) in the x1/x2/x3 output structs.
//   (2) p010LSB2MSBNeon         (libAlgoProcess.so)       — fix the conversion length w5.
//
// Run:  frida -U -n com.oplus.camera -l op_chroma_repair.js   (needs `adb root` + frida-server)
// Take an Auto/HDR photo of a HIGH-DR scene:
//   sharp + correctly-colored JPEG  => bug is the same, offsets (incl. +0x40 pitch anchor) correct
//                                       => the native libapsfixup.so will work identically.
//   green/garbage chroma or crash   => struct anchor differs; use op_outstruct_dump.js to re-derive.

'use strict';

function rangeOf(ptr) {
  const r = Process.findRangeByAddress(ptr);
  return r ? { base: r.base, size: r.size } : null;
}
// valid camera buffer VA: high 32 bits 0x70..0x7f, low >= 0x100000
function isBuf(v) {
  const hi = v.shr(32).toUInt32();
  const lo = v.and(0xffffffff).toUInt32();
  return hi >= 0x70 && hi <= 0x7f && lo >= 0x100000;
}
// garbage chroma ptr: same high range, tiny/zeroed low part
function isGarbage(v) {
  const hi = v.shr(32).toUInt32();
  const lo = v.and(0xffffffff).toUInt32();
  return hi >= 0x70 && hi <= 0x7f && lo < 0x100000;
}

function repairStruct(p) {
  if (p.isNull()) return;
  if (!rangeOf(p)) return;
  for (let off = 0; off + 16 <= 0x80; off += 8) {
    const luma = p.add(off).readU64();
    const chroma = p.add(off + 8).readU64();
    if (isBuf(luma) && isGarbage(chroma)) {
      const lr = rangeOf(ptr(luma.toString()));
      if (!lr) continue;
      const avail = lr.base.add(lr.size).sub(ptr(luma.toString()));
      const ysize = avail.mul(2).div(3).and(ptr('0xfffffffffffff000')); // page-aligned 2/3
      p.add(off + 8).writeU64(ptr(luma.toString()).add(ysize));
      if (off === 0x40) {                                  // pitch[1]@+0x64 = pitch[0]@+0x60
        const yp = p.add(0x60).readU32();
        if (yp > 0 && p.add(0x64).readU32() === 0) p.add(0x64).writeU32(yp);
      }
      console.log('[repair] chroma @+0x' + off.toString(16) + ' luma=' + luma +
                  ' ysize=' + ysize);
    }
  }
}

const arc = Module.findExportByName('libarcsoft_turbo_raw.so', 'ARC_Turbo_RAW_Process');
if (arc) {
  Interceptor.attach(arc, { onEnter(a) { repairStruct(a[1]); repairStruct(a[2]); repairStruct(a[3]); } });
  console.log('[hook] ARC_Turbo_RAW_Process @ ' + arc);
} else {
  console.log('[!] ARC_Turbo_RAW_Process not found (lib not loaded yet?)');
}

const p010 = Module.findExportByName('libAlgoProcess.so',
  '_ZN22APSFormatConverterNeon15p010LSB2MSBNeonEPtS0_jjjj');
if (p010) {
  Interceptor.attach(p010, {
    onEnter(a) {
      const src = a[1];
      const w4 = a[4].toUInt32();
      if (w4 > 0) {
        const sr = rangeOf(src);
        if (sr) {
          const avail = sr.base.add(sr.size).sub(src);
          const newW5 = avail.mul(2).div(3).div(w4).toUInt32();
          const oldW5 = a[5].toUInt32();
          if (newW5 > 0 && newW5 !== oldW5) {
            console.log('[p010] w5 ' + oldW5 + ' -> ' + newW5 + ' (w4=' + w4 + ' avail=' + avail + ')');
            a[5] = ptr(newW5);
          }
        }
      }
    }
  });
  console.log('[hook] p010LSB2MSBNeon @ ' + p010);
} else {
  console.log('[!] p010LSB2MSBNeon not found');
}
