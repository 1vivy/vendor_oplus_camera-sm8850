# OP15 (infiniti) OCS smali patches

Applied at extraction time by `extract-files.py`'s
`blob_fixup().apktool_patch('patches')` hook (apktool decode -> `git apply` ->
apktool build -> stripzip). Patches are fingerprint-anchored (context lines),
NOT line-number based.

## 0001-BaseMode-IS_OPLUS_PACKAGE-identity.patch

- **Target blob:** `com.oplus.camera.unit.sdk.jar` (system_ext/framework) —
  NOT OplusCamera.apk. Verified: the APK's dex contains no
  `Util;->isSystemCamera()Z` / `IS_OPLUS_PACKAGE` symbols; the SDK jar's
  `com/oplus/ocs/camera/producer/mode/BaseMode.smali` does.
- **Method:** `updateStageParameterBuilder(...)`, the `"configure"` stage case.
- **Change:** NOP the `if-nez p2, :cond_25` guard immediately after
  `invoke-static Util;->isSystemCamera()Z`. Source intent:
  `if (!isSystemCamera() && useOplusCameraCase(stage)) set(IS_OPLUS_PACKAGE,{1})`.
  Removing the `if-nez` (skip-when-isSystemCamera) lets the SYSTEM camera fall
  through to the `useOplusCameraCase` check and self-stamp `IS_OPLUS_PACKAGE={1}`,
  so the provider's `InitPackageName` resolves the Oplus identity gate (+0x36F0=1)
  and selects the SAT-Fusion offline-reprocess pipeline instead of the bare graph.
- **Provenance:** the proven on-device capture unblock (project RE notes /
  MEMORY). Verified here statically: patch applies cleanly via `git apply`, and
  after a full apktool decode->patch->build round-trip the rebuilt classes.dex
  re-baksmalis with the `nop` in place at the IS_OPLUS_PACKAGE site.

The dodge OP13 font patch was intentionally NOT carried (obfuscated class names
differ between the OP13 and OP15 APKs).
