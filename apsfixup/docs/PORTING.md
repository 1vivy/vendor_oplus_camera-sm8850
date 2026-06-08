# libapsfixup — sm8850 (infiniti) port notes & device-validation

Ported from spkal01's `device_oneplus_dodge/apsfixup` (OnePlus 13, sm8750). Same Oplus camera
stack; the mechanism is identical, only the offsets are re-derived for our blobs. See
`../../docs/rearch/19-spkal01-dodge-shim.md` and `20-gralloc-master.md` for the full background.

## What it does (one paragraph)

The port's gralloc hands a **non-contiguous P010 plane layout** to the byte-identical
ArcSoft/Algo blobs (A16 Gralloc5 `AHardwareBuffer_lockPlanes` per-plane-VA contract). The blobs
assume contiguous semi-planar (Cb = Y + stride·height), so they compute a garbage chroma pointer,
a zero chroma stride, and a garbage P010-conversion length → ~1 GB walk off a 36 MB dmabuf →
SIGSEGV. `libapsfixup.so` is a device-built `cc_library_shared` installed to `/odm/lib64`,
injected as a `DT_NEEDED` of `libAlgoProcess.so` (extract-files `.add_needed`), and exposed in
`public.libraries.txt`. At load it does two **GOT/PLT JUMP_SLOT** redirects (mprotect RW →
overwrite data ptr → mprotect RO; no code patch, no execmem) and corrects the consumed values:
(1) chroma ptr = luma + Ysize (page-aligned 2/3·avail), (2) chroma pitch = Y pitch, (3) p010
length `w5 = (2/3·avail)/w4`. Keyed to the garbage-chroma signature → no-op on correct buffers.

## sm8850 offsets (re-derived; static confidence noted)

| constant | sm8850 (ours) | dodge (sm8750) | how derived | confidence |
|---|---|---|---|---|
| `p010LSB2MSBNeon` vaddr | `0x4fc094` | `0x4bd934` | `readelf -s` `_ZN22APSFormatConverterNeon15p010LSB2MSBNeonEPtS0_jjjj` | **HIGH (static)** |
| `P010_GOT_OFF` (libAlgoProcess) | **`0x689ba8`** | `0x62db58` | `readelf -r` R_AARCH64_JUMP_SLOT for that symbol | **HIGH (static)** |
| `DLSYM_GOT_OFF` (libAlgoInterface) | **`0x1bb67c8`** | `0x23c8c58` | `readelf -r` `dlsym@LIBC` JUMP_SLOT | **HIGH (static)** |
| ARC dlsym symbol | `ARC_Turbo_RAW_Process` | (same) | exact string + `find ARC_Turbo_RAW_Process failed!! dlerror:%s` | **HIGH (static)** |
| struct: luma/chroma/pitch[0]/pitch[1] | `+0x40 / +0x48 / +0x60 / +0x64` | (same) | inherited from dodge | **MEDIUM — needs frida** |

Blobs: `libAlgoProcess.so` BuildID `82fe443b408f8ed027558b0d4ffb1500`,
`libAlgoInterface.so` BuildID `ce6e40ca2e987fcc6da26930d84b0b2f`.
Both are **BIND_NOW** (eager GOT) and the GOT slots are inside **PT_GNU_RELRO** → the mprotect
RW/RO dance is required (handled by `got_redirect`).

### Why the struct offsets are MEDIUM confidence

`repair_struct` SCANS the passed struct (`0x00`..`0x78`, 8-byte stride) for the
valid-luma(`0x76..`)/garbage-chroma(`0x77..`) signature, so the **chroma-pointer fix is
offset-agnostic** and robust regardless of the exact layout. The ONLY device-specific hardcode is
the **chroma-pitch fix**, anchored at `off == 0x40` → reads Y pitch at `+0x60`, writes chroma
pitch at `+0x64`. If our ArcSoft output struct places the luma/chroma pair at a different offset,
the chroma-ptr fix still fires (scan finds it) but the pitch fix would not → chroma stride stays 0
→ wrong/green chroma may persist.

Static RE this session could not cleanly pin the anchor: the struct is filled by
`libAlgoInterface` (dlsym-indirected fnptr) and `ARC_Turbo_RAW_Process`'s decompiled signature is
too mangled (Ghidra recovered 19 params) to read the field offsets confidently. **However**, our
`libarcsoft_turbo_raw.so` is **byte-identical to stock** (md5 `0c8775f4…`) and both OP13/OP15 ship
the same A16 ArcSoft Turbo-RAW SDK vintage, so the struct ABI is very likely identical to dodge.
**Confirm on device with the frida probe below before dropping the binary geometry patch.**

## Device validation (THE acceptance test)

This shim and the binary `min()` geometry patch (`f3f372e`) fix the SAME bug. Keep the binary
patch as fallback; validate the shim, then drop the binary patch.

1. Build + flash a userdebug image with `libapsfixup` packaged (Phase 2 wiring).
2. `adb root` (frida needs it), push frida-server, run `op_chroma_repair.js` (this dir,
   `docs/frida/`) — it implements the SAME three corrections in JS by hooking the two functions by
   name. Take an **Auto / HDR photo of a high-DR scene**.
   - **Sharp + correctly-colored JPEG** ⇒ the bug is the same and the offsets (incl. the +0x40
     pitch anchor) are correct → the native `libapsfixup.so` will work identically.
   - **Green/garbage chroma or crash** ⇒ the struct anchor differs; run `op_outstruct_dump.js`
     (dump the x1/x2/x3 structs at `ARC_Turbo_RAW_Process` entry) to read the real luma/chroma/
     pitch offsets, then update `repair_struct`'s `off == 0x40` / `+0x60` / `+0x64` constants.
3. With the native shim in place (no frida), repeat the high-DR Auto/HDR capture: the p010 crash
   (`p010LSB2MSBNeon` in tombstones) must NOT recur and the JPEG must be sharp + correct color.
4. Only after step 3 passes, remove the binary `min()`/described-height patch from
   `libAlgoProcess.so` (revert `f3f372e`) and re-validate.

### Frida one-liners (quick offset checks on a stock/dev device)

```js
// confirm p010LSB2MSBNeon is hookable by name and see its (w4,w5) args
Interceptor.attach(Module.getExportByName('libAlgoProcess.so',
    '_ZN22APSFormatConverterNeon15p010LSB2MSBNeonEPtS0_jjjj'), {
  onEnter(a){ console.log('p010 w4='+a[4].toInt32()+' w5='+a[5].toInt32()+' src='+a[1]); }
});

// dump the ARC input structs to find the real luma/chroma/pitch offsets (x1,x2,x3)
Interceptor.attach(Module.getExportByName('libarcsoft_turbo_raw.so','ARC_Turbo_RAW_Process'), {
  onEnter(a){ for (const r of [a[1],a[2],a[3]]) {
    if (r.isNull()) continue;
    console.log('--- struct '+r);
    for (let o=0; o<0x80; o+=8) console.log('  +0x'+o.toString(16)+': '+r.add(o).readU64()); }
  }
});
```

`ARC_Turbo_RAW_Process` is exported by our `libarcsoft_turbo_raw.so` at vaddr `0x20d34`;
`p010LSB2MSBNeon` is a `GLOBAL` dynsym in `libAlgoProcess.so` at `0x4fc094` — both hookable by
name (no offset hardcode needed in the probe).
