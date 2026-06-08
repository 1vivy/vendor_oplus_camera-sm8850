// SPDX-License-Identifier: Apache-2.0
//
// libapsfixup.so — OnePlus 15 (infiniti / sm8850) APS / gralloc P010 plane-layout fix.
//
// Ported from spkal01's device_oneplus_dodge/apsfixup (OnePlus 13, sm8750) — same Oplus
// camera stack, sister SoC. This is a FIRST-PARTY, source-built cc_library_shared, NOT a
// blob patch: it leaves the (wrong) gralloc plane layout in place and corrects the values
// the byte-identical ArcSoft/Algo blobs CONSUME, via GOT/PLT JUMP_SLOT interposition
// (mprotect RW -> overwrite data pointer -> mprotect RO; no code patch, no execmem).
//
// ──────────────────────────────────────────────────────────────────────────────────────
// Root cause (verbatim from doc 19/20):
//   The port's gralloc returns a NON-CONTIGUOUS P010 plane layout for the 12.5 MP P010
//   capture output (4096x3072, byte-stride 8192) to the byte-identical ArcSoft/Algo blobs,
//   which assume contiguous semi-planar (Cb = Y + stride*height). The blobs then compute a
//   garbage chroma plane pointer (align_up(luma,0) ~= 4GB), a zero chroma stride, and run
//   the P010 LSB->MSB conversion with a garbage source length -> ~1 GB walk off a 36 MB
//   dmabuf -> SIGSEGV. This is the A16 Gralloc5 AHardwareBuffer_lockPlanes per-plane-VA
//   contract (system-wide, mapper.qti byte-identical) — a consumer-side correction is the
//   robust, blast-radius-free fix.
//
// Three corrections (4:2:0 semi-planar P010, Y plane = 2/3 of the contiguous dmabuf):
//   (1) chroma plane ptr  : plane[1] (UV) = luma + Ysize, Ysize = (avail*2/3) page-aligned
//   (2) chroma pitch       : pitch[1] = pitch[0] (Y stride)   (was 0)
//   (3) p010 conv length   : w5 = (2/3*avail)/w4  so w4*w5*1.5 == buffer (no overrun)
//
// Engages ONLY when the chroma plane is actually garbage (valid 0x76.. luma ptr immediately
// followed by a 0x77..-range garbage chroma ptr); a no-op on correct buffers.
//
// ──────────────────────────────────────────────────────────────────────────────────────
// sm8850 (infiniti) re-derived offsets — DO NOT reuse the dodge/sm8750 values.
// Derived statically (readelf -r / -s) from:
//   libAlgoProcess.so  BuildID 82fe443b408f8ed027558b0d4ffb1500
//   libAlgoInterface.so BuildID ce6e40ca2e987fcc6da26930d84b0b2f
//
//   constant          sm8850 (ours)   meaning                                 lib
//   P010_FUNC_VADDR   0x4fc094        APSFormatConverterNeon::p010LSB2MSBNeon  libAlgoProcess
//   P010_GOT_OFF      0x689ba8        its R_AARCH64_JUMP_SLOT GOT entry        libAlgoProcess
//   DLSYM_GOT_OFF     0x1bb67c8       dlsym@LIBC JUMP_SLOT GOT entry           libAlgoInterface
//   ARC symbol        "ARC_Turbo_RAW_Process"  (string-matched in wrap_dlsym)
//   struct fields     +0x40 luma / +0x48 chroma / +0x60 pitch[0] / +0x64 pitch[1]
//                     ^ INHERITED FROM dodge — the chroma-ptr fix is offset-agnostic (scans
//                       0x00..0x78); only the pitch anchor (off==0x40 -> +0x60/+0x64) is
//                       device-specific. Pending on-device frida confirmation via
//                       docs/frida/op_chroma_repair.js (sharp + correct color == offsets OK).
//
#include <cstdint>
#include <cinttypes>
#include <cstring>
#include <cstdio>
#include <unistd.h>
#include <pthread.h>
#include <sys/mman.h>
#include <link.h>

#define LOG_TAG "apsfixup"
#include <log/log.h>

// ── sm8850 offsets ──────────────────────────────────────────────────────────────────────
static constexpr uintptr_t P010_GOT_OFF  = 0x689ba8;   // libAlgoProcess.so
static constexpr uintptr_t DLSYM_GOT_OFF = 0x1bb67c8;  // libAlgoInterface.so
static constexpr const char* LIB_PROCESS   = "libAlgoProcess.so";
static constexpr const char* LIB_INTERFACE = "libAlgoInterface.so";
static constexpr const char* ARC_SYMBOL    = "ARC_Turbo_RAW_Process";

// ── real function pointers (filled by the GOT redirects) ──────────────────────────────────
using p010_fn_t  = void (*)(uint16_t*, uint16_t*, uint32_t, uint32_t, uint32_t, uint32_t);
using dlsym_fn_t = void* (*)(void*, const char*);

static p010_fn_t  g_real_p010  = nullptr;
// hidden -> non-preemptible, so the wrap_arc naked asm can use PC-relative adrp/:lo12: (a
// preemptible global would force a GOT reference the naked asm doesn't emit). `used` because
// it is referenced ONLY from inline asm, which LTO cannot see (would otherwise drop it).
extern "C" __attribute__((visibility("hidden"), used)) void* aps_real_arc = nullptr;
static dlsym_fn_t g_real_dlsym = nullptr;

static bool g_done_p010  = false;
static bool g_done_dlsym = false;

// ── /proc/self/maps range lookup: the mapping [base,base+size) containing addr ─────────────
static bool range_of(uint64_t addr, uint64_t* base, uint64_t* size) {
    FILE* f = fopen("/proc/self/maps", "re");
    if (!f) return false;
    char line[512];
    bool found = false;
    while (fgets(line, sizeof(line), f)) {
        uint64_t lo = 0, hi = 0;
        if (sscanf(line, "%" SCNx64 "-%" SCNx64, &lo, &hi) != 2) continue;
        if (addr >= lo && addr < hi) {
            if (base) *base = lo;
            if (size) *size = hi - lo;
            found = true;
            break;
        }
    }
    fclose(f);
    return found;
}

// valid camera buffer VA: high 32 bits in 0x70..0x7f and a sane low offset
static inline bool is_buf(uint64_t v) {
    uint32_t hi = (uint32_t)(v >> 32);
    uint32_t lo = (uint32_t)(v & 0xffffffffULL);
    return hi >= 0x70 && hi <= 0x7f && lo >= 0x100000;
}
// garbage chroma ptr: same high range, but a tiny/zeroed low part (align_up(luma,0) etc.)
static inline bool is_garbage(uint64_t v) {
    uint32_t hi = (uint32_t)(v >> 32);
    uint32_t lo = (uint32_t)(v & 0xffffffffULL);
    return hi >= 0x70 && hi <= 0x7f && lo < 0x100000;
}

// ── GOT/PLT JUMP_SLOT redirect (relro: mprotect RW, overwrite data ptr, mprotect RO) ──────
static bool got_redirect(uintptr_t slot, void* newval, void** old) {
    void** got = (void**)slot;
    uintptr_t page = slot & ~(uintptr_t)0xfff;
    if (mprotect((void*)page, 0x1000, PROT_READ | PROT_WRITE) != 0) {
        ALOGE("mprotect RW failed for slot %p", (void*)slot);
        return false;
    }
    if (old) *old = *got;
    *got = newval;
    mprotect((void*)page, 0x1000, PROT_READ);
    return true;
}

// ── chroma struct repair: rewrite the garbage Cb plane ptr (+ pitch[1] at the +0x40 plane) ──
static void repair_struct(void* p) {
    if (!p) return;
    uint64_t mb, ms;
    if (!range_of((uint64_t)p, &mb, &ms)) return;
    uint8_t* b = (uint8_t*)p;
    for (int off = 0; off + 16 <= 0x80; off += 8) {
        uint64_t luma   = *(uint64_t*)(b + off);
        uint64_t chroma = *(uint64_t*)(b + off + 8);
        if (is_buf(luma) && is_garbage(chroma)) {
            uint64_t lb, ls;
            if (!range_of(luma, &lb, &ls)) continue;
            uint64_t avail = (lb + ls) - luma;
            uint64_t ysize = (avail * 2 / 3) & ~0xfffULL;   // Y-plane size, page aligned
            *(uint64_t*)(b + off + 8) = luma + ysize;       // plane[1] (UV) ptr
            if (off == 0x40) {                              // pitch[1]@+0x64 = pitch[0]@+0x60
                uint32_t yp = *(uint32_t*)(b + 0x60);
                if (yp > 0 && *(uint32_t*)(b + 0x64) == 0) *(uint32_t*)(b + 0x64) = yp;
            }
            ALOGI("repaired chroma plane @+0x%x: luma=%p -> chroma=%p (ysize=0x%llx)",
                  off, (void*)luma, (void*)(luma + ysize), (unsigned long long)ysize);
        }
    }
}

// ARC_Turbo_RAW_Process gets up to three ArcSoft output structs (x1/x2/x3); repair each.
// `used` — called ONLY from the wrap_arc inline asm (invisible to LTO).
extern "C" __attribute__((visibility("hidden"), used))
void aps_repair_structs(void* s1, void* s2, void* s3) {
    repair_struct(s1);
    repair_struct(s2);
    repair_struct(s3);
}

// Naked trampoline: save x0-x7 + x30, call aps_repair_structs(orig x1,x2,x3), restore,
// pop our frame so the caller's stack args are intact, then tail-call the real ARC.
extern "C" __attribute__((naked, visibility("hidden"))) void wrap_arc() {
    asm volatile(
        "stp x0, x1, [sp, #-0x50]!\n"
        "stp x2, x3, [sp, #0x10]\n"
        "stp x4, x5, [sp, #0x20]\n"
        "stp x6, x7, [sp, #0x30]\n"
        "str x30,    [sp, #0x40]\n"
        "mov x0, x1\n"                 // aps_repair_structs(orig x1, orig x2, orig x3)
        "mov x1, x2\n"
        "mov x2, x3\n"
        "bl  aps_repair_structs\n"
        "ldr x30,    [sp, #0x40]\n"
        "ldp x6, x7, [sp, #0x30]\n"
        "ldp x4, x5, [sp, #0x20]\n"
        "ldp x2, x3, [sp, #0x10]\n"
        "ldp x0, x1, [sp], #0x50\n"
        "adrp x16, aps_real_arc\n"
        "ldr  x16, [x16, #:lo12:aps_real_arc]\n"
        "br   x16\n"
    );
}

// dlsym interposer: when libAlgoInterface resolves ARC_Turbo_RAW_Process, hand back the
// wrapper so the engine stores wrap_arc (which repairs the structs before each call).
static void* wrap_dlsym(void* handle, const char* symbol) {
    void* res = g_real_dlsym(handle, symbol);
    if (symbol && res && strcmp(symbol, ARC_SYMBOL) == 0) {
        aps_real_arc = res;
        ALOGI("intercepted dlsym(%s) -> wrap_arc (real=%p)", symbol, res);
        return (void*)wrap_arc;
    }
    return res;
}

// p010LSB2MSBNeon(dst, src, w2, w3, w4, w5): recompute the conversion length w5 so the loop
// spans exactly the Y+UV bytes (w4*w5*1.5 == buffer) instead of a garbage source stride.
static void wrap_p010(uint16_t* dst, uint16_t* src,
                      uint32_t w2, uint32_t w3, uint32_t w4, uint32_t w5) {
    if (w4 > 0) {
        uint64_t sb, ss;
        if (range_of((uint64_t)src, &sb, &ss)) {
            uint64_t avail  = (sb + ss) - (uint64_t)src;
            uint32_t new_w5 = (uint32_t)((avail * 2 / 3) / w4);   // w4*w5*1.5 == buffer
            if (new_w5 > 0 && new_w5 != w5) {
                ALOGI("p010 length fix: w5 %u -> %u (w4=%u avail=0x%llx)",
                      w5, new_w5, w4, (unsigned long long)avail);
                w5 = new_w5;
            }
        }
    }
    g_real_p010(dst, src, w2, w3, w4, w5);
}

// ── locate the load bias of a named DT_NEEDED object via dl_iterate_phdr ───────────────────
struct find_ctx { const char* name; uintptr_t base; };
static int find_cb(struct dl_phdr_info* info, size_t, void* data) {
    auto* ctx = (find_ctx*)data;
    if (info->dlpi_name && strstr(info->dlpi_name, ctx->name)) {
        ctx->base = (uintptr_t)info->dlpi_addr;
        return 1;
    }
    return 0;
}
static uintptr_t module_base(const char* name) {
    find_ctx ctx{name, 0};
    dl_iterate_phdr(find_cb, &ctx);
    return ctx.base;
}

// Install both GOT redirects. Idempotent; returns true once BOTH have landed.
static bool try_install() {
    if (!g_done_p010) {
        uintptr_t base = module_base(LIB_PROCESS);
        if (base) {
            void* old = nullptr;
            if (got_redirect(base + P010_GOT_OFF, (void*)wrap_p010, &old)) {
                g_real_p010 = (p010_fn_t)old;
                g_done_p010 = true;
                ALOGI("hooked p010LSB2MSBNeon GOT @%p (real=%p)",
                      (void*)(base + P010_GOT_OFF), old);
            }
        }
    }
    if (!g_done_dlsym) {
        uintptr_t base = module_base(LIB_INTERFACE);
        if (base) {
            void* old = nullptr;
            if (got_redirect(base + DLSYM_GOT_OFF, (void*)wrap_dlsym, &old)) {
                g_real_dlsym = (dlsym_fn_t)old;
                g_done_dlsym = true;
                ALOGI("hooked dlsym GOT @%p (real=%p)",
                      (void*)(base + DLSYM_GOT_OFF), old);
            }
        }
    }
    return g_done_p010 && g_done_dlsym;
}

// Fallback poller: libAlgoInterface may load after us (dlopen'd post-cap). Retry every 25ms
// for ~10 min until both hooks land, then exit.
static void* poller(void*) {
    for (int i = 0; i < 24000; ++i) {
        if (try_install()) break;
        usleep(25 * 1000);
    }
    return nullptr;
}

__attribute__((constructor)) static void apsfixup_init() {
    ALOGI("libapsfixup loaded (sm8850 P010 plane-layout fix)");
    if (try_install()) return;
    pthread_t t;
    if (pthread_create(&t, nullptr, poller, nullptr) == 0) {
        pthread_detach(t);
    }
}
