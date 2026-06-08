#!/usr/bin/env -S PYTHONPATH=../../../tools/extract-utils python3
#
# SPDX-FileCopyrightText: 2016 The CyanogenMod Project
# SPDX-FileCopyrightText: 2017-2024 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

from extract_utils.fixups_lib import (
    lib_fixups,
    lib_fixups_user_type,
)
from extract_utils.fixups_blob import (
    blob_fixup,
    blob_fixups_user_type,
)
from extract_utils.main import (
    ExtractUtils,
    ExtractUtilsModule,
)


def lib_fixup_system_ext_suffix(lib: str, partition: str, *args, **kwargs):
    """
    Mirrors lib_to_package_fixup_system_ext_variants from the old setup-makefiles.sh.
    These libs exist as system_ext variants and need a _system_ext suffix
    when pulled from that partition.
    """
    if partition != 'system_ext':
        return None

    system_ext_libs = {
        'libSuperTextWrapper',
        'libXDocProcessSDK',
        'libYTCommon',
        'libmpbase',
        'libextendfile',
    }

    return f'{lib}_system_ext' if lib in system_ext_libs else None


lib_fixups: lib_fixups_user_type = {
    # **lib_fixups already includes the clang RT ubsan and proto 3.9.1
    # fixups that were previously handled by the bash helper functions
    # lib_to_package_fixup_clang_rt_ubsan_standalone and
    # lib_to_package_fixup_proto_3_9_1 — no need to add them explicitly.
    **lib_fixups,
    (
        'libSuperTextWrapper',
        'libXDocProcessSDK',
        'libYTCommon',
        'libmpbase',
        'libextendfile',
    ): lib_fixup_system_ext_suffix,
}

# IS_OPLUS_PACKAGE identity patch (the proven on-device capture unblock; see
# project RE notes / MEMORY). The BaseMode "configure"-stage smali that
# self-stamps IS_OPLUS_PACKAGE lives in com.oplus.camera.unit.sdk.jar (NOT in
# OplusCamera.apk — verified: the OplusCamera.apk dex files contain no
# Util;->isSystemCamera()Z / IS_OPLUS_PACKAGE symbols, whereas the SDK jar's
# producer/mode/BaseMode.smali does). The patch NOPs the `if-nez p2, :cond_25`
# guard following `Util;->isSystemCamera()Z` in updateStageParameterBuilder so
# the SYSTEM camera no longer skips the stamp and self-tags as an Oplus package.
# apktool decodes/rebuilds the framework jar the same way it does an APK;
# patches/ is fingerprint-anchored (8 lines of context, label/instruction
# neighborhood), not line-number based.
blob_fixups: blob_fixups_user_type = {
    'system_ext/framework/com.oplus.camera.unit.sdk.jar': blob_fixup()
        .apktool_patch('patches'),
}  # fmt: skip

namespace_imports = [
    'vendor/oplus/camera-sm8850/camera',
    'vendor/oneplus/infiniti',
    'vendor/oneplus/sm8850-common',
    'hardware/oplus',
]

module = ExtractUtilsModule(
    'camera',
    'oplus/camera-sm8850',
    device_rel_path='vendor/oplus/camera-sm8850',
    blob_fixups=blob_fixups,
    lib_fixups=lib_fixups,
    namespace_imports=namespace_imports,
)

if __name__ == '__main__':
    utils = ExtractUtils.device(module)
    utils.run()
