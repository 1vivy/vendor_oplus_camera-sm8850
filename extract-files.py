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
    apktool_path,
    blob_fixup,
    blob_fixups_user_type,
    java_path,
)
from extract_utils.main import (
    ExtractUtils,
    ExtractUtilsModule,
)
from extract_utils.utils import run_cmd
from pathlib import Path
import re
import shutil


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
    **lib_fixups,
    (
        'libSuperTextWrapper',
        'libXDocProcessSDK',
        'libYTCommon',
        'libmpbase',
        'libextendfile',
    ): lib_fixup_system_ext_suffix,
}



def _noop_smali_method(data: str, signature: str) -> str:
    return re.sub(
        rf'(?ms)^\.method {re.escape(signature)}\n.*?^\.end method',
        f'.method {signature}\n'
        '    .locals 0\n'
        '\n'
        '    return-void\n'
        '.end method',
        data,
    )


def _replace_smali_method(data: str, signature: str, body: str) -> str:
    return re.sub(
        rf'(?ms)^\.method {re.escape(signature)}\n.*?^\.end method',
        f'.method {signature}\n{body}.end method',
        data,
    )


def _empty_map_smali_body() -> str:
    return (
        '    .locals 1\n'
        '\n'
        '    invoke-static {}, Ljava/util/Collections;->emptyMap()Ljava/util/Map;\n'
        '\n'
        '    move-result-object v0\n'
        '\n'
        '    return-object v0\n'
    )


def blob_fixup_apktool_unpack_src(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    if tmp_dir is None:
        return

    run_cmd([
        java_path,
        '-Xmx8g',
        '-jar',
        apktool_path,
        'd',
        file_path,
        '-o',
        tmp_dir,
        '-f',
        '--no-res',
    ])


def blob_fixup_apktool_unpack_full(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    if tmp_dir is None:
        return

    run_cmd([
        java_path,
        '-Xmx8g',
        '-jar',
        apktool_path,
        'd',
        file_path,
        '-o',
        tmp_dir,
        '-f',
    ])


def blob_fixup_opluscamera_oppo_component_safe(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    if tmp_dir is None:
        return

    manifest = Path(tmp_dir) / 'AndroidManifest.xml'
    data = manifest.read_text(encoding='utf-8') if manifest.exists() else ''
    permission = '    <uses-permission android:name="oppo.permission.OPPO_COMPONENT_SAFE"/>\n'
    if 'oppo.permission.OPPO_COMPONENT_SAFE' not in data:
        data = data.replace(
            '    <uses-permission android:name="oplus.permission.OPLUS_COMPONENT_SAFE"/>\n',
            '    <uses-permission android:name="oplus.permission.OPLUS_COMPONENT_SAFE"/>\n'
            + permission,
            1,
        )
        manifest.write_text(data, encoding='utf-8')


def blob_fixup_opluscamera_uses_library(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    # Text-manifest variant (for apks unpacked with a full apktool decode, e.g.
    # OppoGallery2.apk). OplusCamera.apk uses the binary-AXML variant
    # (blob_fixup_opluscamera_manifest_axml) because it is unpacked --no-res. See the
    # com.oplus.wrapper.* / oplus.camera.stubs rationale on that function.
    if tmp_dir is None:
        return

    manifest = Path(tmp_dir) / 'AndroidManifest.xml'
    data = manifest.read_text(encoding='utf-8') if manifest.exists() else ''
    if not data or 'oplus.camera.stubs' in data:
        return
    entry = '        <uses-library android:name="oplus.camera.stubs" android:required="false"/>\n'
    if '</application>' in data:
        data = data.replace('</application>', entry + '    </application>', 1)
        manifest.write_text(data, encoding='utf-8')


def blob_fixup_opluscamera_manifest_axml(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    # Resource-faithful manifest patch (binary AXML, via pyaxml).
    #
    # The OplusCamera.apk is unpacked with apktool --no-res (blob_fixup_apktool_unpack_src)
    # so resources.arsc is kept RAW and copied back verbatim on build. This is REQUIRED:
    # a full apktool decode rebuilds resources.arsc with legacy aapt, which drops the
    # non-default locale config rows (camera renders zh on an en device) AND renumbers
    # app resource IDs (FileProvider @xml ref breaks). Keeping resources.arsc byte-identical
    # to stock also preserves the AE/HDR/tuning config rows (a full-decode rebuild blew out
    # preview highlights). Verified with aapt2: resources.arsc stays byte-identical and the
    # added <uses-library> is recognized.
    #
    # Cost of --no-res: AndroidManifest.xml stays BINARY (apktool only decodes the manifest
    # to text when it also decodes resources). So we patch the binary AXML directly to add
    # the two entries the LOS port needs, replacing the old text-based uses_library +
    # oppo_component_safe fixups:
    #   - <uses-library oplus.camera.stubs required=false>: the com.oplus.wrapper.* /
    #     com.oplus.flexiblewindow.* classes live in oplus-framework.jar (BOOTCLASSPATH) on
    #     stock; we ship them as the off-bootclasspath shared lib oplus.camera.stubs
    #     (oplus-camera-stubs.jar, declared in privapp-permissions-oplus.xml), so the app's
    #     own classloader needs this <uses-library> to resolve them.
    #   - <uses-permission oppo.permission.OPPO_COMPONENT_SAFE> (legacy component-safe perm).
    # Idempotent (skips if oplus.camera.stubs is already declared). NB: requires pyaxml
    # (pip install pyaxml) in the extract environment.
    if tmp_dir is None:
        return

    import pyaxml
    from lxml import etree

    ANDROID = 'http://schemas.android.com/apk/res/android'
    manifest = Path(tmp_dir) / 'AndroidManifest.xml'
    if not manifest.exists():
        return

    axml = pyaxml.AXML.from_axml(manifest.read_bytes())
    root = axml.to_xml()
    app = root.find('application')
    changed = False
    if app is not None and not any(
        e.get(f'{{{ANDROID}}}name') == 'oplus.camera.stubs'
        for e in app.findall('uses-library')
    ):
        ul = etree.SubElement(app, 'uses-library')
        ul.set(f'{{{ANDROID}}}name', 'oplus.camera.stubs')
        ul.set(f'{{{ANDROID}}}required', 'false')
        changed = True
    if not any(
        e.get(f'{{{ANDROID}}}name') == 'oppo.permission.OPPO_COMPONENT_SAFE'
        for e in root.findall('uses-permission')
    ):
        up = etree.SubElement(root, 'uses-permission')
        up.set(f'{{{ANDROID}}}name', 'oppo.permission.OPPO_COMPONENT_SAFE')
        changed = True
    if changed:
        out = pyaxml.AXML()
        out.from_xml(root)
        manifest.write_bytes(out.pack())


def blob_fixup_oplus_camera_system_properties(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    if tmp_dir is None:
        return

    for smali in Path(tmp_dir).glob('smali*/**/*.smali'):
        data = smali.read_text(encoding='utf-8')
        fixed = data.replace(
            'Lcom/oplus/wrapper/os/SystemProperties;',
            'Landroid/os/SystemProperties;',
        )
        if fixed != data:
            smali.write_text(fixed, encoding='utf-8')


def blob_fixup_oplus_camera_framework_shims(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    if tmp_dir is None:
        return

    for smali in Path(tmp_dir).glob('smali*/**/*.smali'):
        data = smali.read_text(encoding='utf-8')
        fixed = data
        for old_tag, new_tag in {
            'com.oplus.capture.flash.need': 'com.oplus.flashtrigger.state',
            'com.oplus.flash.status': 'com.oplus.flashtrigger.state',
            'com.oplus.outflash.flashtype': 'com.oplus.flashtrigger.state',
            'com.oplus.preview.outflash.connected': 'com.oplus.flashtrigger.state',
            'com.oplus.DolIsStaggerState': 'com.oplus.capture.request.idx',
            'com.oplus.iris.aperture.switching': 'com.oplus.capture.request.idx',
            'com.oplus.control.face.dr': 'com.oplus.capture.request.idx',
            'com.oplus.fallback.stable': 'com.oplus.capture.request.idx',
            'com.oplus.capture.request.need.preview.stream': 'com.oplus.capture.request.idx',
            'com.oplus.filter.mode': 'com.oplus.capture.request.idx',
            'com.oplus.app.filter.type': 'com.oplus.capture.request.idx',
            'com.oplus.aicolor.rear.enable': 'com.oplus.capture.request.idx',
            'com.oplus.camera.3d.api.state': 'com.oplus.capture.request.idx',
            'com.oplus.camera.configure.thermal.level': 'com.oplus.capture.request.idx',
            'com.oplus.camera.pi.enable': 'com.oplus.capture.request.idx',
            'com.oplus.camera.pi.enable_list': 'com.oplus.capture.request.idx',
            'com.oplus.asd.hdr.scope': 'com.oplus.capture.request.idx',
            'com.oplus.night.se.enable': 'com.oplus.capture.request.idx',
            'com.oplus.preview.ai.preset.asd.enable': 'com.oplus.capture.request.idx',
            'com.oplus.aec.customAE.enable': 'com.oplus.macro.closeup.enable',
            'com.oplus.lsd.enable': 'com.oplus.capture.request.idx',
            'com.oplus.only.zoom.change': 'com.oplus.capture.request.idx',
            'com.oplus.config.aeExposureCompensation': 'com.oplus.capture.request.idx',
            'com.oplus.naturetone.state': 'com.oplus.capture.request.idx',
            'com.oplus.hal.fluency': 'com.oplus.capture.request.idx',
            'com.oplus.double.ois.wirecutoff.detection.sn': 'com.oplus.capture.request.idx',
            'com.oplus.izoom.ability.support': 'com.oplus.aps.zoom.feature',
            'com.oplus.mipiraw.online.bpc': 'com.oplus.capture.mipiraw.online.bpc',
            'com.oplus.algo.visualization.enable': 'com.oplus.multiobj.info.visualization',
            'com.oplus.camera.algo.visualization.enable': 'com.oplus.multiobj.info.visualization',
            'com.oplus.sod.enable': 'com.oplus.sod.touch.region',
            'com.oplus.process.pid': 'com.oplus.capture.request.idx',
            'com.oplus.caller.package.name': 'com.oplus.packageName',
            'com.oplus.camera.is.turn.on': 'com.oplus.is.sdk.camera.package',
            'com.oplus.device.orientation': 'com.oplus.preview.orientation',
            'com.oplus.TR.processing.state': 'com.oplus.capture.request.idx',
            'com.oplus.capture.request.idx_list': 'com.oplus.capture.request.idx',
            'com.oplus.facebeauty.custom': 'com.oplus.facebeauty.level',
            'com.oplus.picture.offset.time': 'com.oplus.capture.request.idx',
        }.items():
            fixed = fixed.replace(old_tag, new_tag)
        fixed = re.sub(
            r'(?m)^\.implements Ljava/lang/Object;\n',
            '',
            fixed,
        )
        fixed = re.sub(
            r'(?m)^(\s*)invoke-virtual \{([vp]\d+)\}, Ljava/lang/Enum;->name\(\)Ljava/lang/String;',
            r'\1invoke-static {\2}, Ljava/lang/String;->valueOf(Ljava/lang/Object;)Ljava/lang/String;',
            fixed,
        )
        if smali.match('*/com/oplus/camera/CameraManager$a.smali'):
            fixed = fixed.replace(
                '    invoke-virtual {p0}, Landroid/os/AsyncTask;->isCancelled()Z\n'
                '\n'
                '    .line 29\n'
                '    .line 30\n'
                '    .line 31\n'
                '    move-result p1\n'
                '\n'
                '    .line 32\n'
                '    if-nez p1, :cond_4\n'
                '\n'
                '    .line 33\n'
                '    .line 34\n'
                '    sget p1, Lqk/p;->p:I\n',
                '    invoke-virtual {p0}, Landroid/os/AsyncTask;->isCancelled()Z\n'
                '\n'
                '    .line 29\n'
                '    .line 30\n'
                '    .line 31\n'
                '    move-result p1\n'
                '\n'
                '    .line 32\n'
                '    if-nez p1, :cond_4\n'
                '\n'
                '    .line 33\n'
                '    .line 34\n'
                '    const/4 p1, 0x0\n',
                1,
            )

        if smali.match('*/in/x0.smali'):
            fixed = _noop_smali_method(fixed, 'public final S6()V')

        if smali.name == 'Performance.smali':
            fixed = _noop_smali_method(fixed, 'public static setIOPriority(I)V')
            fixed = _noop_smali_method(fixed, 'private static synthetic lambda$registerOsenseEventCallback$44()V')
            fixed = _noop_smali_method(fixed, 'private static registerOsenseEventCallback()V')
            fixed = _noop_smali_method(fixed, 'private static unregisterOsenseEventCallback()V')
            fixed = _noop_smali_method(fixed, 'public static requestLongTimeTaskMode()V')
            fixed = _noop_smali_method(fixed, 'public static cancelLongTimeTaskMode()V')

        if False and smali.match('*/com/oplus/ocs/camera/CameraUnitImpl$4.smali'):
            fixed = _noop_smali_method(fixed, 'public run()V')

        if False and smali.match('*/com/oplus/ocs/camera/CameraUnitImpl.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public isAuthedClient(Landroid/content/Context;)Z',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x1\n'
                '\n'
                '    return v0\n',
            )

        if smali.match('*/com/oplus/aiunit/configuration/OSRepository.smali'):
            empty_map_body = _empty_map_smali_body()
            for signature in (
                'private final listFilesFromOS(Ljava/lang/String;Ljava/lang/String;)Ljava/util/Map;',
                'public static synthetic listFilesFromOS$default(Lcom/oplus/aiunit/configuration/OSRepository;Ljava/lang/String;Ljava/lang/String;ILjava/lang/Object;)Ljava/util/Map;',
                'private final listFilesFromOsV2(Ljava/lang/String;)Ljava/util/Map;',
                'public final listPreinstalledOap2(Landroid/content/Context;)Ljava/util/Map;',
                'public final listPreinstalledOapOaa2(Landroid/content/Context;)Ljava/util/Map;',
                'private final readFilesFromOS(Ljava/lang/String;)Ljava/util/Map;',
                'private final readFilesFromOsV2(Ljava/lang/String;)Ljava/util/Map;',
                'public final readPreInstalledOrangeResConfig()Ljava/util/Map;',
                'public final readPreInstalledUnitConfig()Ljava/util/Map;',
                'public final readPreInstalledUnitConfigV2()Ljava/util/Map;',
            ):
                fixed = _replace_smali_method(fixed, signature, empty_map_body)

        if False and smali.match('*/com/oplus/ocs/camera/producer/info/CameraCharacteristicsHelper.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public static getCameraIdType(Ljava/lang/String;)Lcom/oplus/ocs/camera/producer/info/CameraIdType;',
                '    .locals 4\n'
                '\n'
                '    sget-object v0, Lcom/oplus/ocs/camera/producer/info/CameraCharacteristicsHelper;->sCameraIdTypeMap:Ljava/util/Map;\n'
                '\n'
                '    invoke-interface {v0, p0}, Ljava/util/Map;->get(Ljava/lang/Object;)Ljava/lang/Object;\n'
                '\n'
                '    move-result-object v1\n'
                '\n'
                '    check-cast v1, Lcom/oplus/ocs/camera/producer/info/CameraIdType;\n'
                '\n'
                '    if-eqz v1, :cond_0\n'
                '\n'
                '    return-object v1\n'
                '\n'
                '    :cond_0\n'
                '    const/4 v2, -0x1\n'
                '\n'
                '    const-string v3, "rear_main"\n'
                '\n'
                '    invoke-virtual {v3, p0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
                '\n'
                '    move-result v3\n'
                '\n'
                '    if-eqz v3, :cond_1\n'
                '\n'
                '    const/4 v2, 0x0\n'
                '\n'
                '    goto :goto_0\n'
                '\n'
                '    :cond_1\n'
                '    const-string v3, "front_main"\n'
                '\n'
                '    invoke-virtual {v3, p0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
                '\n'
                '    move-result v3\n'
                '\n'
                '    if-eqz v3, :cond_2\n'
                '\n'
                '    const/4 v2, 0x1\n'
                '\n'
                '    goto :goto_0\n'
                '\n'
                '    :cond_2\n'
                '    const-string v3, "rear_wide"\n'
                '\n'
                '    invoke-virtual {v3, p0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
                '\n'
                '    move-result v3\n'
                '\n'
                '    if-eqz v3, :cond_3\n'
                '\n'
                '    const/4 v2, 0x2\n'
                '\n'
                '    goto :goto_0\n'
                '\n'
                '    :cond_3\n'
                '    const-string v3, "rear_tele"\n'
                '\n'
                '    invoke-virtual {v3, p0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
                '\n'
                '    move-result v3\n'
                '\n'
                '    if-eqz v3, :cond_4\n'
                '\n'
                '    const/4 v2, 0x3\n'
                '\n'
                '    goto :goto_0\n'
                '\n'
                '    :cond_4\n'
                '    const-string v3, "rear_ultra_tele"\n'
                '\n'
                '    invoke-virtual {v3, p0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
                '\n'
                '    move-result v3\n'
                '\n'
                '    if-eqz v3, :cond_5\n'
                '\n'
                '    const/4 v2, 0x4\n'
                '\n'
                '    goto :goto_0\n'
                '\n'
                '    :cond_5\n'
                '    const-string v3, "rear_main_front_main"\n'
                '\n'
                '    invoke-virtual {v3, p0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
                '\n'
                '    move-result v3\n'
                '\n'
                '    if-eqz v3, :cond_6\n'
                '\n'
                '    const/16 v2, 0x64\n'
                '\n'
                '    :cond_6\n'
                '    :goto_0\n'
                '    if-ltz v2, :cond_7\n'
                '\n'
                '    new-instance v1, Lcom/oplus/ocs/camera/producer/info/CameraIdType;\n'
                '\n'
                '    invoke-direct {v1, p0, v2}, Lcom/oplus/ocs/camera/producer/info/CameraIdType;-><init>(Ljava/lang/String;I)V\n'
                '\n'
                '    invoke-interface {v0, p0, v1}, Ljava/util/Map;->put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;\n'
                '\n'
                '    sget-object p0, Lcom/oplus/ocs/camera/producer/info/CameraCharacteristicsHelper;->sCameraIdArray:Landroid/util/SparseArray;\n'
                '\n'
                '    invoke-virtual {p0, v2, v1}, Landroid/util/SparseArray;->put(ILjava/lang/Object;)V\n'
                '\n'
                '    return-object v1\n'
                '\n'
                '    :cond_7\n'
                '    const/4 p0, 0x0\n'
                '\n'
                '    return-object p0\n',
            )
            fixed = fixed.replace(
                '    .line 123\n'
                '    :goto_3\n'
                '    sget-object v12, Lcom/oplus/ocs/camera/producer/info/CameraCharacteristicsWrapper;->KEY_AVAILABLE_STREAM_FPS_RANGES:Landroid/hardware/camera2/CameraCharacteristics$Key;\n',
                '    .line 123\n'
                '    :goto_3\n'
                '    const-string v13, "0"\n'
                '\n'
                '    invoke-virtual {v13, v7}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
                '\n'
                '    move-result v13\n'
                '\n'
                '    if-eqz v13, :cond_op15_camera_type_1\n'
                '\n'
                '    const/4 v10, 0x0\n'
                '\n'
                '    goto :cond_op15_camera_type_done\n'
                '\n'
                '    :cond_op15_camera_type_1\n'
                '    const-string v13, "1"\n'
                '\n'
                '    invoke-virtual {v13, v7}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
                '\n'
                '    move-result v13\n'
                '\n'
                '    if-eqz v13, :cond_op15_camera_type_2\n'
                '\n'
                '    const/4 v10, 0x1\n'
                '\n'
                '    goto :cond_op15_camera_type_done\n'
                '\n'
                '    :cond_op15_camera_type_2\n'
                '    const-string v13, "2"\n'
                '\n'
                '    invoke-virtual {v13, v7}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
                '\n'
                '    move-result v13\n'
                '\n'
                '    if-eqz v13, :cond_op15_camera_type_3\n'
                '\n'
                '    const/4 v10, 0x2\n'
                '\n'
                '    goto :cond_op15_camera_type_done\n'
                '\n'
                '    :cond_op15_camera_type_3\n'
                '    const-string v13, "3"\n'
                '\n'
                '    invoke-virtual {v13, v7}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
                '\n'
                '    move-result v13\n'
                '\n'
                '    if-eqz v13, :cond_op15_camera_type_4\n'
                '\n'
                '    const/4 v10, 0x6\n'
                '\n'
                '    goto :cond_op15_camera_type_done\n'
                '\n'
                '    :cond_op15_camera_type_4\n'
                '    const-string v13, "4"\n'
                '\n'
                '    invoke-virtual {v13, v7}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
                '\n'
                '    move-result v13\n'
                '\n'
                '    if-eqz v13, :cond_op15_camera_type_done\n'
                '\n'
                '    const/16 v10, 0x1a\n'
                '\n'
                '    :cond_op15_camera_type_done\n'
                '    sget-object v12, Lcom/oplus/ocs/camera/producer/info/CameraCharacteristicsWrapper;->KEY_AVAILABLE_STREAM_FPS_RANGES:Landroid/hardware/camera2/CameraCharacteristics$Key;\n',
            )

        if False and smali.match('*/com/oplus/ocs/camera/producer/device/Camera2Impl.smali'):
            fixed = fixed.replace(
                '    .line 2976\n'
                '    iget-object p0, p0, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->mDeviceVariable:Landroid/os/ConditionVariable;\n'
                '\n'
                '    invoke-virtual {p0}, Landroid/os/ConditionVariable;->block()V\n',
                '    .line 2976\n'
                '    invoke-direct {p0}, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->closeAllImageReader()V\n'
                '\n'
                '    iget-object v1, p0, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->mCameraStateCallback:Landroid/hardware/camera2/CameraDevice$StateCallback;\n'
                '\n'
                '    if-eqz v1, :cond_op15_direct_closed_callback\n'
                '\n'
                '    iget-object v2, p0, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->mCameraDevice:Landroid/hardware/camera2/CameraDevice;\n'
                '\n'
                '    invoke-virtual {v1, v2}, Landroid/hardware/camera2/CameraDevice$StateCallback;->onClosed(Landroid/hardware/camera2/CameraDevice;)V\n'
                '\n'
                '    :cond_op15_direct_closed_callback\n'
                '    iget-object v1, p0, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->mDeviceVariable:Landroid/os/ConditionVariable;\n'
                '\n'
                '    invoke-virtual {v1}, Landroid/os/ConditionVariable;->open()V\n'
                '\n'
                '    const/4 v1, 0x0\n'
                '\n'
                '    iput-object v1, p0, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->mCameraDevice:Landroid/hardware/camera2/CameraDevice;\n',
            )
            fixed = fixed.replace(
                '    if-nez v1, :cond_0\n'
                '\n'
                '    return-void\n'
                '\n'
                '    .line 2905\n'
                '    :cond_0\n'
                '    invoke-virtual {p0, v1}, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->updateOplusParams(Landroid/hardware/camera2/CameraManager;)V\n',
                '    if-nez v1, :cond_0\n'
                '\n'
                '    return-void\n'
                '\n'
                '    .line 2905\n'
                '    :cond_0\n'
                '    const/16 v2, 0x64\n'
                '\n'
                '    if-ne p1, v2, :cond_0_op15_real_id\n'
                '\n'
                '    const/4 p1, 0x0\n'
                '\n'
                '    :cond_0_op15_real_id\n'
                '    invoke-virtual {p0, v1}, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->updateOplusParams(Landroid/hardware/camera2/CameraManager;)V\n',
            )
        if False and smali.match('*/com/oplus/ocs/camera/producer/device/Camera2Impl$2.smali'):
            fixed = fixed.replace(
                '.method public onClosed(Landroid/hardware/camera2/CameraDevice;)V\n'
                '    .locals 2\n',
                '.method public onClosed(Landroid/hardware/camera2/CameraDevice;)V\n'
                '    .locals 3\n',
            )
            fixed = fixed.replace(
                '    const-string v1, "StateCallback"\n'
                '\n'
                '    invoke-static {v1, v0}, Lcom/oplus/ocs/camera/common/util/CameraUnitLog;->w(Ljava/lang/String;Ljava/lang/String;)V\n'
                '\n'
                '    .line 350\n'
                '    iget-object v0, p0, Lcom/oplus/ocs/camera/producer/device/Camera2Impl$2;->this$0:Lcom/oplus/ocs/camera/producer/device/Camera2Impl;\n',
                '    const-string v1, "StateCallback"\n'
                '\n'
                '    invoke-static {v1, v0}, Lcom/oplus/ocs/camera/common/util/CameraUnitLog;->w(Ljava/lang/String;Ljava/lang/String;)V\n'
                '\n'
                '    iget-object v2, p0, Lcom/oplus/ocs/camera/producer/device/Camera2Impl$2;->this$0:Lcom/oplus/ocs/camera/producer/device/Camera2Impl;\n'
                '\n'
                '    invoke-static {v2}, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->-$$Nest$fgetmCameraStateCallback(Lcom/oplus/ocs/camera/producer/device/Camera2Impl;)Landroid/hardware/camera2/CameraDevice$StateCallback;\n'
                '\n'
                '    move-result-object v2\n'
                '\n'
                '    if-eqz v2, :cond_op15_on_closed_forwarded\n'
                '\n'
                '    invoke-virtual {v2, p1}, Landroid/hardware/camera2/CameraDevice$StateCallback;->onClosed(Landroid/hardware/camera2/CameraDevice;)V\n'
                '\n'
                '    :cond_op15_on_closed_forwarded\n'
                '    .line 350\n'
                '    iget-object v0, p0, Lcom/oplus/ocs/camera/producer/device/Camera2Impl$2;->this$0:Lcom/oplus/ocs/camera/producer/device/Camera2Impl;\n',
            )
        if False and smali.match('*/com/oplus/ocs/camera/producer/device/Camera2Impl$12.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public execute(Ljava/lang/Runnable;)V',
                '    .locals 0\n'
                '\n'
                '    invoke-interface {p1}, Ljava/lang/Runnable;->run()V\n'
                '\n'
                '    return-void\n',
            )

        if False and smali.match('*/com/oplus/ocs/camera/producer/device/Camera2Impl$7.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public onConfigured(Landroid/hardware/camera2/CameraCaptureSession;)V',
                '    .locals 3\n'
                '\n'
                '    .line 838\n'
                '    new-instance v0, Ljava/lang/StringBuilder;\n'
                '\n'
                '    const-string v1, "onConfigured,"\n'
                '\n'
                '    invoke-direct {v0, v1}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V\n'
                '\n'
                '    invoke-virtual {v0, p1}, Ljava/lang/StringBuilder;->append(Ljava/lang/Object;)Ljava/lang/StringBuilder;\n'
                '\n'
                '    invoke-virtual {v0}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;\n'
                '\n'
                '    move-result-object v0\n'
                '\n'
                '    const-string v1, "StateCallback"\n'
                '\n'
                '    invoke-static {v1, v0}, Lcom/oplus/ocs/camera/common/util/CameraUnitLog;->w(Ljava/lang/String;Ljava/lang/String;)V\n'
                '\n'
                '    const-string v0, "CameraUnit.CameraStartupPerformance.onCameraCaptureSessionConfigured"\n'
                '\n'
                '    .line 840\n'
                '    invoke-static {v0}, Lcom/oplus/ocs/camera/common/util/CameraUnitLog;->traceBeginSection(Ljava/lang/String;)V\n'
                '\n'
                '    .line 842\n'
                '    iget-object v1, p0, Lcom/oplus/ocs/camera/producer/device/Camera2Impl$7;->this$0:Lcom/oplus/ocs/camera/producer/device/Camera2Impl;\n'
                '\n'
                '    invoke-static {v1, p1}, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->-$$Nest$fputmCaptureSession(Lcom/oplus/ocs/camera/producer/device/Camera2Impl;Landroid/hardware/camera2/CameraCaptureSession;)V\n'
                '\n'
                '    move-object v2, p1\n'
                '\n'
                '    .line 843\n'
                '    iget-object p1, p0, Lcom/oplus/ocs/camera/producer/device/Camera2Impl$7;->this$0:Lcom/oplus/ocs/camera/producer/device/Camera2Impl;\n'
                '\n'
                '    invoke-static {p1}, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->-$$Nest$fgetmSessionVariable(Lcom/oplus/ocs/camera/producer/device/Camera2Impl;)Landroid/os/ConditionVariable;\n'
                '\n'
                '    move-result-object p1\n'
                '\n'
                '    invoke-virtual {p1}, Landroid/os/ConditionVariable;->open()V\n'
                '\n'
                '    iget-object p1, p0, Lcom/oplus/ocs/camera/producer/device/Camera2Impl$7;->this$0:Lcom/oplus/ocs/camera/producer/device/Camera2Impl;\n'
                '\n'
                '    invoke-static {p1}, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->-$$Nest$fgetmCameraSessionCallback(Lcom/oplus/ocs/camera/producer/device/Camera2Impl;)Landroid/hardware/camera2/CameraCaptureSession$StateCallback;\n'
                '\n'
                '    move-result-object p1\n'
                '\n'
                '    if-eqz p1, :cond_0_op15_config_forwarded\n'
                '\n'
                '    invoke-virtual {p1, v2}, Landroid/hardware/camera2/CameraCaptureSession$StateCallback;->onConfigured(Landroid/hardware/camera2/CameraCaptureSession;)V\n'
                '\n'
                '    :cond_0_op15_config_forwarded\n'
                '    .line 844\n'
                '    iget-object p0, p0, Lcom/oplus/ocs/camera/producer/device/Camera2Impl$7;->this$0:Lcom/oplus/ocs/camera/producer/device/Camera2Impl;\n'
                '\n'
                '    const/4 p1, 0x0\n'
                '\n'
                '    invoke-static {p0, p1}, Lcom/oplus/ocs/camera/producer/device/Camera2Impl;->-$$Nest$fputmbNotAllowedTakePicture(Lcom/oplus/ocs/camera/producer/device/Camera2Impl;Z)V\n'
                '\n'
                '    .line 846\n'
                '    invoke-static {v0}, Lcom/oplus/ocs/camera/common/util/CameraUnitLog;->traceEndSection(Ljava/lang/String;)V\n'
                '\n'
                '    return-void\n',
            )

        if False and smali.match('*/com/oplus/ocs/camera/producer/device/CameraSessionEntity.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public getOperationMode()I',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n',
            )
            fixed = _replace_smali_method(
                fixed,
                'public setOperationMode(Ljava/lang/String;)V',
                '    .locals 1\n'
                '\n'
                '    const-string v0, "0"\n'
                '\n'
                '    iput-object v0, p0, Lcom/oplus/ocs/camera/producer/device/CameraSessionEntity;->mOperationMode:Ljava/lang/String;\n'
                '\n'
                '    return-void\n',
            )

        if False and smali.match('*/com/oplus/ocs/camera/producer/ProducerImpl$DefaultCameraStateCallbackAdapter.smali'):
            fixed = fixed.replace(
                '    .line 1508\n'
                '    :goto_1\n'
                '    invoke-static {}, Lcom/oplus/ocs/camera/platform/PlatformUtil;->getPlatformFlag()Ljava/lang/String;\n',
                '    .line 1508\n'
                '    :goto_1\n'
                '    const-string p1, "OP15Retry"\n'
                '\n'
                '    const-string v0, "onCameraOpened retryPendingPreview"\n'
                '\n'
                '    invoke-static {p1, v0}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I\n'
                '\n'
                '    move-result p1\n'
                '\n'
                '    iget-object p1, p0, Lcom/oplus/ocs/camera/producer/ProducerImpl$DefaultCameraStateCallbackAdapter;->this$0:Lcom/oplus/ocs/camera/producer/ProducerImpl;\n'
                '\n'
                '    iget-object v0, p0, Lcom/oplus/ocs/camera/producer/ProducerImpl$DefaultCameraStateCallbackAdapter;->mHandler:Landroid/os/Handler;\n'
                '\n'
                '    invoke-virtual {p1, v0}, Lcom/oplus/ocs/camera/producer/ProducerImpl;->retryPendingPreview(Landroid/os/Handler;)V\n'
                '\n'
                '    invoke-static {}, Lcom/oplus/ocs/camera/platform/PlatformUtil;->getPlatformFlag()Ljava/lang/String;\n',
                1,
            )
            fixed = fixed.replace(
                '    invoke-virtual {p1}, Landroid/os/ConditionVariable;->open()V\n'
                '\n'
                '    .line 1661\n'
                '    iget-object p1, p0, Lcom/oplus/ocs/camera/producer/ProducerImpl$DefaultCameraStateCallbackAdapter;->mHandler:Landroid/os/Handler;\n',
                '    invoke-virtual {p1}, Landroid/os/ConditionVariable;->open()V\n'
                '\n'
                '    iget-object p1, p0, Lcom/oplus/ocs/camera/producer/ProducerImpl$DefaultCameraStateCallbackAdapter;->this$0:Lcom/oplus/ocs/camera/producer/ProducerImpl;\n'
                '\n'
                '    iget-object v0, p0, Lcom/oplus/ocs/camera/producer/ProducerImpl$DefaultCameraStateCallbackAdapter;->mHandler:Landroid/os/Handler;\n'
                '\n'
                '    invoke-virtual {p1, v0}, Lcom/oplus/ocs/camera/producer/ProducerImpl;->retryPendingPreview(Landroid/os/Handler;)V\n'
                '\n'
                '    .line 1661\n'
                '    iget-object p1, p0, Lcom/oplus/ocs/camera/producer/ProducerImpl$DefaultCameraStateCallbackAdapter;->mHandler:Landroid/os/Handler;\n',
            )

        if smali.match('*/com/oplus/ocs/camera/producer/ProducerImpl.smali'):
            fixed = fixed.replace(
                '    .line 139\n'
                '    iput-boolean p1, p0, Lcom/oplus/ocs/camera/producer/ProducerImpl;->mbManageMultiDevice:Z\n',
                '    .line 139\n'
                '    const/4 p1, 0x0\n'
                '\n'
                '    iput-boolean p1, p0, Lcom/oplus/ocs/camera/producer/ProducerImpl;->mbManageMultiDevice:Z\n',
                1,
            )
            fixed = fixed.replace(
                '    invoke-virtual {v0}, Lcom/oplus/ocs/camera/producer/device/CameraSessionEntity;->getOperationMode()I\n'
                '\n'
                '    move-result p5\n',
                '    invoke-virtual {v0}, Lcom/oplus/ocs/camera/producer/device/CameraSessionEntity;->getOperationMode()I\n'
                '\n'
                '    move-result p5\n'
                '\n'
                '    const/4 p5, 0x0\n',
                1,
            )
            # Do not replay cached preview or force photo_mode/rear camera here.
            # Those hacks can keep the display path tied to the old camera during switches.
            fixed = _replace_smali_method(
                fixed,
                'public setParameter(Landroid/hardware/camera2/CaptureRequest$Key;Ljava/lang/Object;)V',
                '    .locals 1\n'
                '\n'
                '    iget-object v0, p0, Lcom/oplus/ocs/camera/producer/ProducerImpl;->mAllStageParameterBuilder:Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;\n'
                '\n'
                '    if-nez v0, :cond_0\n'
                '\n'
                '    new-instance v0, Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;\n'
                '\n'
                '    invoke-direct {v0}, Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;-><init>()V\n'
                '\n'
                '    iput-object v0, p0, Lcom/oplus/ocs/camera/producer/ProducerImpl;->mAllStageParameterBuilder:Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;\n'
                '\n'
                '    :cond_0\n'
                '    invoke-virtual {v0, p1, p2}, Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;->set(Landroid/hardware/camera2/CaptureRequest$Key;Ljava/lang/Object;)Lcom/oplus/ocs/camera/metadata/parameter/Parameter$BaseBuilder;\n'
                '\n'
                '    return-void\n',
            )
            fixed = _replace_smali_method(
                fixed,
                'public setParameter(Ljava/lang/String;Ljava/lang/Object;)V',
                '    .locals 1\n'
                '\n'
                '    iget-object v0, p0, Lcom/oplus/ocs/camera/producer/ProducerImpl;->mAllStageParameterBuilder:Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;\n'
                '\n'
                '    if-nez v0, :cond_0\n'
                '\n'
                '    new-instance v0, Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;\n'
                '\n'
                '    invoke-direct {v0}, Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;-><init>()V\n'
                '\n'
                '    iput-object v0, p0, Lcom/oplus/ocs/camera/producer/ProducerImpl;->mAllStageParameterBuilder:Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;\n'
                '\n'
                '    :cond_0\n'
                '    invoke-virtual {v0, p1, p2}, Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter$Builder;->set(Ljava/lang/String;Ljava/lang/Object;)Lcom/oplus/ocs/camera/metadata/parameter/Parameter$BaseBuilder;\n'
                '\n'
                '    return-void\n',
            )
            # Keep original null-current-mode behavior instead of silently creating
            # a rear photo mode during switch/startPreview.

        if smali.match('*/tk/e0.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public static i()Z',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n',
            )
            fixed = _noop_smali_method(fixed, 'public final A(I)V')
            fixed = _noop_smali_method(fixed, 'public final u(Z)V')
            fixed = _noop_smali_method(fixed, 'public final z()V')

        if smali.match('*/d9/c.smali'):
            fixed = _noop_smali_method(fixed, 'public final run()V')

        if smali.match('*/wl/h.smali'):
            fixed = _noop_smali_method(fixed, 'public final run()V')

        if smali.match('*/nj/d.smali'):
            fixed = fixed.replace(
                '.method public final g7(II)V\n'
                '    .locals 6\n',
                '.method public final g7(II)V\n'
                '    .locals 6\n'
                '\n'
                '    const-string v0, "OP15Switch"\n'
                '\n'
                '    new-instance v1, Ljava/lang/StringBuilder;\n'
                '\n'
                '    const-string v2, "g7 target="\n'
                '\n'
                '    invoke-direct {v1, v2}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V\n'
                '\n'
                '    invoke-virtual {v1, p1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;\n'
                '\n'
                '    const-string v2, " openType="\n'
                '\n'
                '    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;\n'
                '\n'
                '    invoke-virtual {v1, p2}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;\n'
                '\n'
                '    const-string v2, " paused="\n'
                '\n'
                '    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;\n'
                '\n'
                '    iget-boolean v2, p0, Lnj/d;->d:Z\n'
                '\n'
                '    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;\n'
                '\n'
                '    const-string v2, " switching="\n'
                '\n'
                '    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;\n'
                '\n'
                '    iget-boolean v2, p0, Lnj/d;->e:Z\n'
                '\n'
                '    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;\n'
                '\n'
                '    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;\n'
                '\n'
                '    move-result-object v1\n'
                '\n'
                '    invoke-static {v0, v1}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I\n'
                '\n'
                '    move-result v0\n',
                1,
            )

        if smali.match('*/uj/g.smali'):
            fixed = fixed.replace(
                '.method public final n(IZ)Z\n'
                '    .locals 6\n',
                '.method public final n(IZ)Z\n'
                '    .locals 6\n'
                '\n'
                '    const-string v0, "OP15Switch"\n'
                '\n'
                '    new-instance v1, Ljava/lang/StringBuilder;\n'
                '\n'
                '    const-string v2, "DeviceProcessor.n entry arg="\n'
                '\n'
                '    invoke-direct {v1, v2}, Ljava/lang/StringBuilder;-><init>(Ljava/lang/String;)V\n'
                '\n'
                '    invoke-virtual {v1, p1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;\n'
                '\n'
                '    const-string v2, " flag="\n'
                '\n'
                '    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;\n'
                '\n'
                '    invoke-virtual {v1, p2}, Ljava/lang/StringBuilder;->append(Z)Ljava/lang/StringBuilder;\n'
                '\n'
                '    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;\n'
                '\n'
                '    move-result-object v1\n'
                '\n'
                '    invoke-static {v0, v1}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I\n'
                '\n'
                '    move-result v0\n',
                1,
            )

        if smali.match('*/com/oplus/camera/feature/integration/mirror/MirrorOplusEdrUtils.smali'):
            fixed = _noop_smali_method(fixed, 'static constructor <clinit>()V')
            fixed = _replace_smali_method(
                fixed,
                'public static setEdrAnimDuration(Landroid/view/SurfaceControl;Landroid/view/SurfaceControl$Transaction;II)Z',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n',
            )
            fixed = _replace_smali_method(
                fixed,
                'public static setEdrSdrRatio(Landroid/view/SurfaceControl;Landroid/view/SurfaceControl$Transaction;F)Z',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n',
            )

        if smali.match('*/t5/x0.smali'):
            fixed = _noop_smali_method(fixed, 'public static varargs c([I)V')
            fixed = _noop_smali_method(fixed, 'public static varargs g(Lt5/x0$a;[I)V')

        if smali.match('*/a7/i3.smali'):
            fixed = _noop_smali_method(fixed, 'static constructor <clinit>()V')
            fixed = fixed.replace(
                'Lcom/oplus/shoulderpressure/OplusShoulderPressureManager;',
                'Ljava/lang/Object;',
            )

        if smali.match('*/a7/c3.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public static a(Landroid/content/Context;)I',
                '    .locals 1\n'
                '\n'
                '    const/16 v0, 0xff\n'
                '\n'
                '    return v0\n'
            )

        if smali.match('*/a7/e1.smali'):
            fixed = _noop_smali_method(fixed, 'public static e(I)V')

        if smali.match('*/s7/p.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public static c(I)Ljava/lang/String;',
                '    .locals 1\n'
                '\n'
                '    packed-switch p0, :pswitch_data_0\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return-object v0\n'
                '\n'
                '    :pswitch_0\n'
                '    const-string v0, "rear_main"\n'
                '\n'
                '    return-object v0\n'
                '\n'
                '    :pswitch_1\n'
                '    const-string v0, "front_main"\n'
                '\n'
                '    return-object v0\n'
                '\n'
                '    :pswitch_2\n'
                '    const-string v0, "rear_wide"\n'
                '\n'
                '    return-object v0\n'
                '\n'
                '    :pswitch_3\n'
                '    const-string v0, "rear_tele"\n'
                '\n'
                '    return-object v0\n'
                '\n'
                '    :pswitch_4\n'
                '    const-string v0, "rear_ultra_tele"\n'
                '\n'
                '    return-object v0\n'
                '\n'
                '    :pswitch_data_0\n'
                '    .packed-switch 0x0\n'
                '        :pswitch_0\n'
                '        :pswitch_1\n'
                '        :pswitch_2\n'
                '        :pswitch_3\n'
                '        :pswitch_4\n'
                '    .end packed-switch\n',
            )

        if smali.match('*/s7/j.smali'):
            fixed = re.sub(
                r'(?ms)^(\s*)invoke-interface \{v0\}, Ljava/util/List;->size\(\)I\n'
                r'\n'
                r'\s*\.line 1062\n'
                r'\s*\.line 1063\n'
                r'\s*\.line 1064\n'
                r'\s*move-result v0\n'
                r'\n'
                r'\s*\.line 1065\n',
                r'\1move v0, v1\n\n    .line 1065\n',
                fixed,
                count=1,
            )

        if smali.match('*/mm/d2.smali') or smali.match('*/mm/h2.smali') or smali.match('*/ai/a.smali'):
            fixed = re.sub(
                r'(?m)^\.implements Landroid/os/OplusKeyEventManager\$OnKeyEventObserver;\n',
                '',
                fixed,
            )

        if smali.match('*/mm/g2.smali'):
            fixed = _noop_smali_method(fixed, 'public final b(Landroid/app/Activity;)V')
            fixed = _noop_smali_method(fixed, 'public final c(Landroid/app/Activity;)V')

        if smali.match('*/mm/i2.smali'):
            fixed = _noop_smali_method(fixed, 'public final b(Landroid/app/Activity;)V')
            fixed = _noop_smali_method(fixed, 'public final c(Landroid/app/Activity;)V')

        if smali.match('*/ai/b.smali'):
            fixed = re.sub(
                r'(?ms)^(\s*)invoke-static \{\}, Landroid/os/OplusKeyEventManager;->getInstance\(\)Landroid/os/OplusKeyEventManager;\n'
                r'.*?^\s*invoke-virtual \{[^}]+\}, Landroid/os/OplusKeyEventManager;->[^\n]+\n'
                r'\s*move-result ([vp]\d+)',
                r'\1const/4 \2, 0x0',
                fixed,
            )
            fixed = re.sub(
                r'(?ms)^(\s*)invoke-static \{\}, Landroid/os/OplusKeyEventManager;->getInstance\(\)Landroid/os/OplusKeyEventManager;\n'
                r'.*?^\s*move-result-object ([vp]\d+)\n'
                r'.*?^\s*invoke-virtual \{[^}]+\}, Landroid/os/OplusKeyEventManager;->[^\n]+\n'
                r'.*?^\s*move-result ([vp]\d+)',
                r'\1const/4 \3, 0x0',
                fixed,
            )

        if smali.match('*/k6/l.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public constructor <init>()V',
                '    .locals 2\n'
                '\n'
                '    invoke-direct {p0}, Ljava/lang/Object;-><init>()V\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    iput-boolean v0, p0, Lk6/l;->a:Z\n'
                '\n'
                '    iput-boolean v0, p0, Lk6/l;->e:Z\n'
                '\n'
                '    iput-boolean v0, p0, Lk6/l;->f:Z\n'
                '\n'
                '    iput v0, p0, Lk6/l;->i:I\n'
                '\n'
                '    iput-boolean v0, p0, Lk6/l;->j:Z\n'
                '\n'
                '    const-wide/16 v0, 0x0\n'
                '\n'
                '    iput-wide v0, p0, Lk6/l;->k:J\n'
                '\n'
                '    return-void\n'
            )
            fixed = _noop_smali_method(fixed, 'public final a(JZ)V')
            fixed = _noop_smali_method(fixed, 'public final b()V')
            fixed = _noop_smali_method(fixed, 'public final c()V')
            fixed = _noop_smali_method(fixed, 'public final d(I)V')
            fixed = _noop_smali_method(fixed, 'public final e()V')
            fixed = _noop_smali_method(fixed, 'public final f()V')
            fixed = _noop_smali_method(fixed, 'public final g(II)V')

        if smali.match('*/k6/l$a.smali'):
            fixed = _noop_smali_method(fixed, 'public final handleMessage(Landroid/os/Message;)V')

        if smali.match('*/p3/a.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public static a(Landroid/content/Context;)Ljava/lang/Object;',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return-object v0\n'
            )
            fixed = _replace_smali_method(
                fixed,
                'public static b(IIII)I',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n'
            )
            fixed = _replace_smali_method(
                fixed,
                'public static c()Z',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n'
            )
            fixed = _noop_smali_method(fixed, 'public static d(Landroid/content/Context;)V')
            fixed = _noop_smali_method(fixed, 'public static e(Ljava/lang/Object;IIIII)V')

        if smali.match('*/eo/j0.smali'):
            fixed = _noop_smali_method(fixed, 'public final b()V')

        if smali.match('*/eo/j0$a.smali') or smali.match('*/com/oplus/camera/feature/out/screen/capture/MultiDisplayManager$e.smali'):
            fixed = _noop_smali_method(fixed, 'public final onActivityEnter(Ljava/lang/Object;)V')
            fixed = _noop_smali_method(fixed, 'public final onActivityExit(Ljava/lang/Object;)V')
            fixed = _noop_smali_method(fixed, 'public final onAppEnter(Ljava/lang/Object;)V')
            fixed = _noop_smali_method(fixed, 'public final onAppExit(Ljava/lang/Object;)V')

        if smali.match('*/eo/s1.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public final a(Landroid/app/Activity;)Z',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n',
            )
            fixed = _noop_smali_method(fixed, 'public final c(Landroid/app/Activity;Lvj/d;)V')
            fixed = _noop_smali_method(fixed, 'public final d()V')
            fixed = _noop_smali_method(fixed, 'public final e()V')

        if smali.match('*/com/oplus/camera/feature/out/screen/capture/MultiDisplayManager.smali'):
            fixed = _noop_smali_method(fixed, 'public h(Landroid/content/Context;)V')

        if smali.match('*/com/oplus/camera/CameraManager.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public static V0()Z',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n',
            )
            fixed = _replace_smali_method(
                fixed,
                'public final m1(Z)V',
                '    .locals 1\n'
                '\n'
                '    iput-boolean p1, p0, Lcom/oplus/camera/CameraManager;->l0:Z\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    iput-boolean v0, p0, Lcom/oplus/camera/CameraManager;->m0:Z\n'
                '\n'
                '    return-void\n',
            )
            fixed = _noop_smali_method(fixed, 'public final F6()V')

        if False and smali.match('*/com/oplus/ocs/camera/CameraDeviceAdapterV2.smali'):
            fixed = fixed.replace(
                '.field private mCameraDeviceInterface:Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;\n',
                '.field private static sOp15LastPreviewAssistCallback:Lcom/oplus/ocs/camera/CameraPreviewAssistCallback;\n'
                '\n'
                '.field private static sOp15LastPreviewCallback:Lcom/oplus/ocs/camera/CameraPreviewCallback;\n'
                '\n'
                '.field private static sOp15LastPreviewHandler:Landroid/os/Handler;\n'
                '\n'
                '.field private static sOp15LastPreviewSurfaces:Ljava/util/Map;\n'
                '\n'
                '.field private static sOp15LastSdkConfig:Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;\n'
                '\n'
                '.field private mCameraDeviceInterface:Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;\n',
                1,
            )
            fixed = _replace_smali_method(
                fixed,
                'public constructor <init>(Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;)V',
                '    .locals 0\n'
                '\n'
                '    invoke-direct {p0}, Lcom/oplus/ocs/camera/CameraDeviceAdapter;-><init>()V\n'
                '\n'
                '    iput-object p1, p0, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->mCameraDeviceInterface:Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;\n'
                '\n'
                '    return-void\n',
            )
            fixed = _replace_smali_method(
                fixed,
                'public configure(Lcom/oplus/ocs/camera/CameraDeviceConfig;)V',
                '    .locals 4\n'
                '\n'
                '    iget-object v0, p0, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->mCameraDeviceInterface:Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;\n'
                '\n'
                '    if-eqz v0, :cond_0\n'
                '\n'
                '    invoke-virtual {p1}, Lcom/oplus/ocs/camera/CameraDeviceConfig;->getConfig()Ljava/lang/Object;\n'
                '\n'
                '    move-result-object v0\n'
                '\n'
                '    instance-of v0, v0, Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;\n'
                '\n'
                '    if-eqz v0, :cond_0\n'
                '\n'
                '    iget-object p0, p0, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->mCameraDeviceInterface:Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;\n'
                '\n'
                '    invoke-virtual {p1}, Lcom/oplus/ocs/camera/CameraDeviceConfig;->getConfig()Ljava/lang/Object;\n'
                '\n'
                '    move-result-object p1\n'
                '\n'
                '    check-cast p1, Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;\n'
                '\n'
                '    sput-object p1, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastSdkConfig:Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;\n'
                '\n'
                '    invoke-interface {p0, p1}, Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;->configure(Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;)V\n'
                '\n'
                '    sget-object p1, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewSurfaces:Ljava/util/Map;\n'
                '\n'
                '    if-eqz p1, :cond_0\n'
                '\n'
                '    sget-object v0, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewCallback:Lcom/oplus/ocs/camera/CameraPreviewCallback;\n'
                '\n'
                '    if-eqz v0, :cond_0\n'
                '\n'
                '    sget-object v1, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewHandler:Landroid/os/Handler;\n'
                '\n'
                '    if-eqz v1, :cond_0\n'
                '\n'
                '    const-string v2, "OP15Preview"\n'
                '\n'
                '    const-string v3, "configure replay cached startPreview"\n'
                '\n'
                '    invoke-static {v2, v3}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I\n'
                '\n'
                '    move-result v2\n'
                '\n'
                '    new-instance v2, Lcom/oplus/ocs/camera/CameraPreviewCallbackAdapterV2;\n'
                '\n'
                '    invoke-direct {v2, v0}, Lcom/oplus/ocs/camera/CameraPreviewCallbackAdapterV2;-><init>(Lcom/oplus/ocs/camera/CameraPreviewCallback;)V\n'
                '\n'
                '    sget-object v0, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewAssistCallback:Lcom/oplus/ocs/camera/CameraPreviewAssistCallback;\n'
                '\n'
                '    new-instance v3, Lcom/oplus/ocs/camera/CameraPreviewAssistCallbackAdapterV2;\n'
                '\n'
                '    invoke-direct {v3, v0}, Lcom/oplus/ocs/camera/CameraPreviewAssistCallbackAdapterV2;-><init>(Lcom/oplus/ocs/camera/CameraPreviewAssistCallback;)V\n'
                '\n'
                '    invoke-interface {p0, p1, v2, v1, v3}, Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;->startPreview(Ljava/util/Map;Lcom/oplus/ocs/camera/appinterface/CameraPreviewCallbackAdapter;Landroid/os/Handler;Lcom/oplus/ocs/camera/appinterface/CameraPreviewAssistCallbackAdapter;)V\n'
                '\n'
                '    :cond_0\n'
                '    return-void\n',
            )
            fixed = _replace_smali_method(
                fixed,
                'public startPreview(Ljava/util/Map;Lcom/oplus/ocs/camera/CameraPreviewCallback;Landroid/os/Handler;Lcom/oplus/ocs/camera/CameraPreviewAssistCallback;)V',
                '    .locals 1\n'
                '    .annotation system Ldalvik/annotation/Signature;\n'
                '        value = {\n'
                '            "(",\n'
                '            "Ljava/util/Map<",\n'
                '            "Ljava/lang/String;",\n'
                '            "Landroid/view/Surface;",\n'
                '            ">;",\n'
                '            "Lcom/oplus/ocs/camera/CameraPreviewCallback;",\n'
                '            "Landroid/os/Handler;",\n'
                '            "Lcom/oplus/ocs/camera/CameraPreviewAssistCallback;",\n'
                '            ")V"\n'
                '        }\n'
                '    .end annotation\n'
                '\n'
                '    sput-object p1, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewSurfaces:Ljava/util/Map;\n'
                '\n'
                '    sput-object p2, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewCallback:Lcom/oplus/ocs/camera/CameraPreviewCallback;\n'
                '\n'
                '    sput-object p3, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewHandler:Landroid/os/Handler;\n'
                '\n'
                '    sput-object p4, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewAssistCallback:Lcom/oplus/ocs/camera/CameraPreviewAssistCallback;\n'
                '\n'
                '    const-string v0, "OP15Preview"\n'
                '\n'
                '    const-string p2, "cache startPreview args"\n'
                '\n'
                '    invoke-static {v0, p2}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I\n'
                '\n'
                '    move-result p2\n'
                '\n'
                '    iget-object p0, p0, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->mCameraDeviceInterface:Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;\n'
                '\n'
                '    if-eqz p0, :cond_0\n'
                '\n'
                '    new-instance v0, Lcom/oplus/ocs/camera/CameraPreviewCallbackAdapterV2;\n'
                '\n'
                '    sget-object p2, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewCallback:Lcom/oplus/ocs/camera/CameraPreviewCallback;\n'
                '\n'
                '    invoke-direct {v0, p2}, Lcom/oplus/ocs/camera/CameraPreviewCallbackAdapterV2;-><init>(Lcom/oplus/ocs/camera/CameraPreviewCallback;)V\n'
                '\n'
                '    new-instance p2, Lcom/oplus/ocs/camera/CameraPreviewAssistCallbackAdapterV2;\n'
                '\n'
                '    invoke-direct {p2, p4}, Lcom/oplus/ocs/camera/CameraPreviewAssistCallbackAdapterV2;-><init>(Lcom/oplus/ocs/camera/CameraPreviewAssistCallback;)V\n'
                '\n'
                '    invoke-interface {p0, p1, v0, p3, p2}, Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;->startPreview(Ljava/util/Map;Lcom/oplus/ocs/camera/appinterface/CameraPreviewCallbackAdapter;Landroid/os/Handler;Lcom/oplus/ocs/camera/appinterface/CameraPreviewAssistCallbackAdapter;)V\n'
                '\n'
                '    :cond_0\n'
                '    return-void\n',
            )
            fixed = fixed.replace(
                '\n.method public resumeRecording()V\n',
                '\n.method public op15ReplayCachedPreview()V\n'
                '    .locals 5\n'
                '\n'
                '    iget-object p0, p0, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->mCameraDeviceInterface:Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;\n'
                '\n'
                '    if-eqz p0, :cond_0\n'
                '\n'
                '    sget-object v0, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastSdkConfig:Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;\n'
                '\n'
                '    if-eqz v0, :cond_op15_no_config\n'
                '\n'
                '    const-string v3, "OP15Preview"\n'
                '\n'
                '    const-string v4, "onOpened replay cached configure"\n'
                '\n'
                '    invoke-static {v3, v4}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I\n'
                '\n'
                '    move-result v3\n'
                '\n'
                '    invoke-interface {p0, v0}, Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;->configure(Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;)V\n'
                '\n'
                '    :cond_op15_no_config\n'
                '    sget-object v0, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewSurfaces:Ljava/util/Map;\n'
                '\n'
                '    if-eqz v0, :cond_0\n'
                '\n'
                '    sget-object v1, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewCallback:Lcom/oplus/ocs/camera/CameraPreviewCallback;\n'
                '\n'
                '    if-eqz v1, :cond_0\n'
                '\n'
                '    sget-object v2, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewHandler:Landroid/os/Handler;\n'
                '\n'
                '    if-eqz v2, :cond_0\n'
                '\n'
                '    const-string v3, "OP15Preview"\n'
                '\n'
                '    const-string v4, "onOpened replay cached startPreview"\n'
                '\n'
                '    invoke-static {v3, v4}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I\n'
                '\n'
                '    move-result v3\n'
                '\n'
                '    new-instance v3, Lcom/oplus/ocs/camera/CameraPreviewCallbackAdapterV2;\n'
                '\n'
                '    invoke-direct {v3, v1}, Lcom/oplus/ocs/camera/CameraPreviewCallbackAdapterV2;-><init>(Lcom/oplus/ocs/camera/CameraPreviewCallback;)V\n'
                '\n'
                '    sget-object v1, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->sOp15LastPreviewAssistCallback:Lcom/oplus/ocs/camera/CameraPreviewAssistCallback;\n'
                '\n'
                '    new-instance v4, Lcom/oplus/ocs/camera/CameraPreviewAssistCallbackAdapterV2;\n'
                '\n'
                '    invoke-direct {v4, v1}, Lcom/oplus/ocs/camera/CameraPreviewAssistCallbackAdapterV2;-><init>(Lcom/oplus/ocs/camera/CameraPreviewAssistCallback;)V\n'
                '\n'
                '    invoke-interface {p0, v0, v3, v2, v4}, Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;->startPreview(Ljava/util/Map;Lcom/oplus/ocs/camera/appinterface/CameraPreviewCallbackAdapter;Landroid/os/Handler;Lcom/oplus/ocs/camera/appinterface/CameraPreviewAssistCallbackAdapter;)V\n'
                '\n'
                '    :cond_0\n'
                '    return-void\n'
                '.end method\n'
                '\n.method public resumeRecording()V\n',
                1,
            )

        if False and smali.match('*/com/oplus/ocs/camera/CameraStateCallbackAdapterV2.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public onCameraOpened(Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;)V',
                '    .locals 2\n'
                '\n'
                '    invoke-super {p0, p1}, Lcom/oplus/ocs/camera/appinterface/CameraStateCallbackAdapter;->onCameraOpened(Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;)V\n'
                '\n'
                '    iget-object p0, p0, Lcom/oplus/ocs/camera/CameraStateCallbackAdapterV2;->mCameraStateCallback:Lcom/oplus/ocs/camera/CameraStateCallback;\n'
                '\n'
                '    new-instance v1, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;\n'
                '\n'
                '    invoke-direct {v1, p1}, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;-><init>(Lcom/oplus/ocs/camera/appinterface/CameraDeviceInterface;)V\n'
                '\n'
                '    if-eqz p0, :cond_0\n'
                '\n'
                '    new-instance v0, Lcom/oplus/ocs/camera/CameraDevice;\n'
                '\n'
                '    invoke-direct {v0, v1}, Lcom/oplus/ocs/camera/CameraDevice;-><init>(Lcom/oplus/ocs/camera/CameraDeviceAdapter;)V\n'
                '\n'
                '    invoke-virtual {p0, v0}, Lcom/oplus/ocs/camera/CameraStateCallback;->onCameraOpened(Lcom/oplus/ocs/camera/CameraDevice;)V\n'
                '\n'
                '    :cond_0\n'
                '    invoke-virtual {v1}, Lcom/oplus/ocs/camera/CameraDeviceAdapterV2;->op15ReplayCachedPreview()V\n'
                '\n'
                '    return-void\n',
            )

        if smali.match('*/com/oplus/ocs/camera/producer/mode/BaseMode.smali'):
            fixed = fixed.replace(
                '    check-cast p2, Lcom/oplus/ocs/camera/common/util/ApsRequestTag;\n'
                '\n'
                '    iput-object p2, v2, Lcom/oplus/ocs/camera/common/util/CameraRequestTag;->mApsRequestTag:Lcom/oplus/ocs/camera/common/util/ApsRequestTag;\n',
                '    check-cast p2, Lcom/oplus/ocs/camera/common/util/ApsRequestTag;\n'
                '\n'
                '    if-nez p2, :cond_op15_aps_tag_ready\n'
                '\n'
                '    new-instance p2, Lcom/oplus/ocs/camera/common/util/ApsRequestTag;\n'
                '\n'
                '    invoke-direct {p2}, Lcom/oplus/ocs/camera/common/util/ApsRequestTag;-><init>()V\n'
                '\n'
                '    iget-object v6, p0, Lcom/oplus/ocs/camera/producer/mode/BaseMode;->mTagMap:Ljava/util/Map;\n'
                '\n'
                '    invoke-interface {v6, p1, p2}, Ljava/util/Map;->put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;\n'
                '\n'
                '    move-result-object v6\n'
                '\n'
                '    :cond_op15_aps_tag_ready\n'
                '    iput-object p2, v2, Lcom/oplus/ocs/camera/common/util/CameraRequestTag;->mApsRequestTag:Lcom/oplus/ocs/camera/common/util/ApsRequestTag;\n',
                1,
            )
            fixed = fixed.replace(
                '    check-cast p2, Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;\n'
                '\n'
                '    .line 1725\n'
                '    invoke-virtual {p2}, Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;->getPictureSurfaces()Ljava/util/List;\n',
                '    check-cast p2, Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;\n'
                '\n'
                '    if-eqz p2, :cond_60\n'
                '\n'
                '    .line 1725\n'
                '    invoke-virtual {p2}, Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;->getPictureSurfaces()Ljava/util/List;\n',
                1,
            )
            fixed = _replace_smali_method(
                fixed,
                'final getConfigureParameter(Ljava/lang/String;)Lcom/oplus/ocs/camera/metadata/parameter/Parameter;',
                '    .locals 2\n'
                '\n'
                '    iget-object p0, p0, Lcom/oplus/ocs/camera/producer/mode/BaseMode;->mConfigMap:Ljava/util/concurrent/ConcurrentHashMap;\n'
                '\n'
                '    invoke-virtual {p0, p1}, Ljava/util/concurrent/ConcurrentHashMap;->get(Ljava/lang/Object;)Ljava/lang/Object;\n'
                '\n'
                '    move-result-object p0\n'
                '\n'
                '    check-cast p0, Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;\n'
                '\n'
                '    if-eqz p0, :cond_0\n'
                '\n'
                '    invoke-virtual {p0}, Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;->getConfigureParameter()Lcom/oplus/ocs/camera/metadata/parameter/Parameter;\n'
                '\n'
                '    move-result-object p0\n'
                '\n'
                '    return-object p0\n'
                '\n'
                '    :cond_0\n'
                '    const-string p0, "OP15Preview"\n'
                '\n'
                '    const-string p1, "missing config, using empty configure parameter"\n'
                '\n'
                '    invoke-static {p0, p1}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I\n'
                '\n'
                '    move-result p0\n'
                '\n'
                '    new-instance p0, Lcom/oplus/ocs/camera/metadata/parameter/ConfigureParameter$Builder;\n'
                '\n'
                '    invoke-direct {p0}, Lcom/oplus/ocs/camera/metadata/parameter/ConfigureParameter$Builder;-><init>()V\n'
                '\n'
                '    invoke-virtual {p0}, Lcom/oplus/ocs/camera/metadata/parameter/ConfigureParameter$Builder;->build()Lcom/oplus/ocs/camera/metadata/parameter/Parameter;\n'
                '\n'
                '    move-result-object p0\n'
                '\n'
                '    return-object p0\n',
            )

        if smali.match('*/a7/l0.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public static m(Ljava/lang/String;)Z',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n',
            )

        # TypeFaceUtil.a(Context)->Typeface: gut-replace the OnePlus custom-font
        # resolver with `return Typeface.DEFAULT` (matches the proven dirtyaf fork
        # 0001-Use-default-font patch). On LOS the OnePlus framework never populates
        # OplusBaseConfiguration->mOplusExtraConfiguration, so the original body NPEs
        # at the `->mFontVariationSettings:I` iget and crashes the camera on open
        # (US-001) + the ai_hint OplusTextView inflate. SIGNATURE-ANCHORED by the
        # method sig + the TypeFaceUtil fingerprint (OplusFontUtils->isFlipFontUsed)
        # so it survives apktool re-obfuscation: committed apk = s7/m3, old fork was
        # a7/u3 / l6/o3. Supersedes the line-anchored NPE-guard (the gut-replace
        # never touches mOplusExtraConfiguration, so the NPE path is gone entirely).
        if (
            'public static a(Landroid/content/Context;)Landroid/graphics/Typeface;' in fixed
            and 'Loplus/content/res/OplusFontUtils;->isFlipFontUsed:Z' in fixed
        ):
            fixed = _replace_smali_method(
                fixed,
                'public static a(Landroid/content/Context;)Landroid/graphics/Typeface;',
                '    .locals 1\n'
                '\n'
                '    sget-object v0, Landroid/graphics/Typeface;->DEFAULT:Landroid/graphics/Typeface;\n'
                '\n'
                '    return-object v0\n',
            )

        # Sibling Configuration->OplusExtraConfiguration accessor (old fork j3/a,
        # committed apk o3/a): return null on LOS, where Configuration is never an
        # OplusBaseConfiguration so there is no mOplusExtraConfiguration to hand back.
        # SIGNATURE-ANCHORED by the return-type signature (the obfuscated class name
        # is not stable across apk rebuilds).
        if 'public static c(Landroid/content/res/Configuration;)Loplus/content/res/OplusExtraConfiguration;' in fixed:
            fixed = _replace_smali_method(
                fixed,
                'public static c(Landroid/content/res/Configuration;)Loplus/content/res/OplusExtraConfiguration;',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return-object v0\n',
            )

        fixed = re.sub(
            r'(?m)^(\s*)invoke-static \{[^}]+\}, Landroid/os/OplusManager;->onStamp\(Ljava/lang/String;Ljava/util/Map;\)V',
            r'\1nop',
            fixed,
        )

        if smali.match('*/pm/l1.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public final b()Z',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n',
            )

        if smali.match('*/l9/a.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public static g(Landroid/bluetooth/BluetoothDevice;)Z',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n',
            )
            fixed = _replace_smali_method(
                fixed,
                'public static i(Landroid/bluetooth/BluetoothDevice;)Z',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n',
            )

        if smali.match('*/eo/a.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public static b(I)I',
                '    .locals 1\n'
                '\n'
                '    invoke-static {}, Landroid/content/res/Resources;->getSystem()Landroid/content/res/Resources;\n'
                '\n'
                '    move-result-object p0\n'
                '\n'
                '    invoke-virtual {p0}, Landroid/content/res/Resources;->getDisplayMetrics()Landroid/util/DisplayMetrics;\n'
                '\n'
                '    move-result-object p0\n'
                '\n'
                '    iget v0, p0, Landroid/util/DisplayMetrics;->densityDpi:I\n'
                '\n'
                '    return v0\n',
            )

        if smali.match('*/com/oplus/camera/util/LayoutUtil.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public static x(Landroid/content/Context;)Z',
                '    .locals 1\n'
                '\n'
                '    const/4 v0, 0x0\n'
                '\n'
                '    return v0\n',
            )

        if smali.match('*/n3/h.smali'):
            fixed = _noop_smali_method(fixed, 'public static e(Landroid/view/View;IIIIII)V')

        if smali.match('*/com/coui/appcompat/dialog/widget/COUIAlertDialogMaxLinearLayout.smali'):
            fixed = _noop_smali_method(fixed, 'private setOutLineProviderInternal(Landroid/graphics/Outline;)V')

        if smali.match('*/com/coui/appcompat/button/COUIButton$a.smali'):
            fixed = _noop_smali_method(fixed, 'public final getOutline(Landroid/view/View;Landroid/graphics/Outline;)V')

        if smali.match('*/com/coui/appcompat/tooltips/COUIToolTips$g.smali'):
            fixed = _noop_smali_method(fixed, 'public final getOutline(Landroid/view/View;Landroid/graphics/Outline;)V')

        if smali.match('*/v7/d.smali'):
            fixed = _noop_smali_method(fixed, 'public final d(Lcom/oplus/camera/MyApplication;)V')
            fixed = _noop_smali_method(fixed, 'public final g()V')

        # NOTE: do NOT blanket-replace com.oplus.wrapper.hardware.devicestate.* with
        # java.lang.Object. oplus-camera-stubs now ships the full wrapper devicestate API
        # (DeviceStateManager + DeviceStateManager$DeviceStateCallback + DeviceState) and
        # com.oplus.devicestate.OplusDeviceStateManager, so OplusDeviceStateManagerCompat
        # resolves against the stubs directly. The old lossy replace was keyed to a stale
        # obfuscated name (v7/d$a); on builds where the class moved (e.g. o8/d$a in
        # v6.070.71) it rewrote `.implements <callback>` into the illegal
        # `.implements Ljava/lang/Object;` (IncompatibleClassChangeError) and turned the
        # register/unregister call sites into Object.registerCallback (NoSuchMethodError).
        # Leaving the wrapper refs intact + complete stubs is correct and obfuscation-proof.

        if smali.match('*/hk/d.smali'):
            fixed = _replace_smali_method(
                fixed,
                'public constructor <init>()V',
                '    .locals 3\n'
                '\n'
                '    invoke-direct {p0}, Ljava/lang/Object;-><init>()V\n'
                '\n'
                '    const/4 v0, 0x1\n'
                '\n'
                '    invoke-static {v0}, Ljava/util/concurrent/Executors;->newScheduledThreadPool(I)Ljava/util/concurrent/ScheduledExecutorService;\n'
                '\n'
                '    move-result-object v1\n'
                '\n'
                '    iput-object v1, p0, Lhk/d;->a:Ljava/util/concurrent/ScheduledExecutorService;\n'
                '\n'
                '    const/4 v1, 0x0\n'
                '\n'
                '    iput-object v1, p0, Lhk/d;->b:Ljava/lang/Object;\n'
                '\n'
                '    new-instance v1, Ljava/util/concurrent/atomic/AtomicInteger;\n'
                '\n'
                '    const/4 v2, 0x0\n'
                '\n'
                '    invoke-direct {v1, v2}, Ljava/util/concurrent/atomic/AtomicInteger;-><init>(I)V\n'
                '\n'
                '    iput-object v1, p0, Lhk/d;->d:Ljava/util/concurrent/atomic/AtomicInteger;\n'
                '\n'
                '    iput-boolean v0, p0, Lhk/d;->e:Z\n'
                '\n'
                '    iput-boolean v2, p0, Lhk/d;->f:Z\n'
                '\n'
                '    new-instance v0, Ljava/lang/Object;\n'
                '\n'
                '    invoke-direct {v0}, Ljava/lang/Object;-><init>()V\n'
                '\n'
                '    iput-object v0, p0, Lhk/d;->h:Ljava/lang/Object;\n'
                '\n'
                '    const/4 v0, -0x1\n'
                '\n'
                '    iput v0, p0, Lhk/d;->i:I\n'
                '\n'
                '    return-void\n',
            )
            fixed = re.sub(
                r'(?m)^(\s*)invoke-virtual \{[^}]+\}, Lcom/oplus/osense/OsenseResEventClient;->requestSceneAction\(Landroid/os/Bundle;\)V',
                r'\1nop',
                fixed,
            )
            fixed = fixed.replace(
                'Lcom/oplus/osense/OsenseResEventClient;',
                'Ljava/lang/Object;',
            )

        if fixed != data:
            smali.write_text(fixed, encoding='utf-8')


def blob_fixup_oplus_camera_typeface_default(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    # TypeFaceUtil.<font>(Context) -> return Typeface.DEFAULT.
    #
    # On the LOS port, OnePlus' framework font-config extension is absent:
    # OplusBaseConfiguration.mOplusExtraConfiguration is null. TypeFaceUtil's font method
    # reads `((OplusBaseConfiguration) cfg).mOplusExtraConfiguration.mFontVariationSettings`
    # inside a try that only catches NoSuchFieldError/NoSuchMethodError -> the NPE escapes and
    # crashes the app whenever a dynamically-inflated OplusTextView/HintTextView is created
    # (AI scene hint, zoom/capture hints via HintManager, face-retouch "Natural" hint, ...).
    # The method already initialises its result to Typeface.DEFAULT and is designed to fall
    # back; we make it return Typeface.DEFAULT unconditionally (cosmetic on LOS: the Oplus
    # custom font isn't installed, so the system default is the correct, stock-equivalent
    # degradation). Same fix both koaaN and spkal01/dodge ship as
    # `0001-Use-default-font-instead-of-OPlus-specific-ones.patch` (their R8 names differ).
    #
    # Anchored by SIGNATURE + body content (the mOplusExtraConfiguration read), NOT the R8
    # method name, so it survives re-obfuscation across APK versions.
    if tmp_dir is None:
        return

    method_re = re.compile(
        r'(\.method [^\n]*\(Landroid/content/Context;\)Landroid/graphics/Typeface;\n)'
        r'(.*?)'
        r'(\n\.end method\n)',
        re.DOTALL,
    )

    def _repl(m):
        if 'OplusBaseConfiguration;->mOplusExtraConfiguration' not in m.group(2):
            return m.group(0)  # not the custom-font method
        return (
            m.group(1)
            + '    .registers 1\n\n'
            + '    sget-object p0, Landroid/graphics/Typeface;->DEFAULT:Landroid/graphics/Typeface;\n\n'
            + '    return-object p0'
            + m.group(3)
        )

    for smali in Path(tmp_dir).glob('smali*/**/*.smali'):
        data = smali.read_text(encoding='utf-8')
        if 'OplusBaseConfiguration;->mOplusExtraConfiguration' not in data:
            continue
        fixed = method_re.sub(_repl, data)
        if fixed != data:
            smali.write_text(fixed, encoding='utf-8')


def blob_fixup_oplus_camera_blur_npe_guard(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    # OplusBlurProcess: null-guard the static int[] read (portrait + front-camera NPE).
    #
    # PORTRAIT > flip-to-selfie crashes with "java.lang.NullPointerException: Attempt to read
    # from null array" at OplusBlurProcess.<m>(II)Z (FATAL on BlurPreviewHandlerThread), and
    # cannot restart (relaunch re-enters portrait+front and re-hits it). The class caches a
    # static `int[]` (R8 name e.g. `w`) populated via OplusBlurPreviewHelper, which returns null
    # on the LOS portrait+front path; the (II)Z init then does `sget-object`+`aget` on it
    # unguarded. Guard each static-int[] read: if null, bail with `monitor-exit` (the method is
    # declared-synchronized) + `return false` — blur-init-failed, so the caller skips the live
    # blur preview (graceful degrade, same philosophy as the TypeFaceUtil default-font fix).
    #
    # Anchored by `.source "OplusBlurProcess.java"` + the synchronized (II)Z method shape and the
    # static `[I` read — NOT the R8 names — so it survives re-obfuscation. Idempotent.
    if tmp_dir is None:
        return

    read_re = re.compile(r'sget-object (v\d+), L[^;]+;->\w+:\[I')

    for smali in Path(tmp_dir).glob('smali*/**/*.smali'):
        data = smali.read_text(encoding='utf-8')
        if '.source "OplusBlurProcess.java"' not in data:
            continue
        if ':aps_wnull' in data:
            continue  # already guarded
        changed = False
        out = []
        last = 0
        for mm in re.finditer(r'(\.method [^\n]*\(II\)Z\n)(.*?)(\n\.end method)', data, re.DOTALL):
            body = mm.group(2)
            if not read_re.search(body):
                continue
            vL = re.search(r'monitor-exit (v\d+)', body)
            vR = re.search(r'\n\s*return (v\d+)', body)
            if not (vL and vR):
                continue  # not the synchronized bool init we expect — leave untouched
            vL, vR = vL.group(1), vR.group(1)
            guarded = read_re.sub(
                lambda m: f'{m.group(0)}\n\n    if-eqz {m.group(1)}, :aps_wnull', body
            )
            guarded += (f'\n\n    :aps_wnull\n    const/16 {vR}, 0x0\n\n'
                        f'    monitor-exit {vL}\n\n    return {vR}')
            out.append(data[last:mm.start()])
            out.append(mm.group(1) + guarded + mm.group(3))
            last = mm.end()
            changed = True
        if changed:
            out.append(data[last:])
            smali.write_text(''.join(out), encoding='utf-8')


def blob_fixup_oplus_camera_surface_transaction_getapply(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    # SurfaceTransaction: add the missing getApply()I getter (return 0).
    #
    # The thumbnail -> in-app gallery "seamless" transition stalls (and the next
    # capture then crashes on the un-restored preview surface) because the
    # SeamlessAnimation builds its per-frame driver as
    #   PropertyValuesHolder.ofInt("apply", new int[]{0})
    # i.e. a SINGLE-value PVH. A single-value ofInt() animates from the property's
    # CURRENT value (read reflectively via the getter getApply()I) to the supplied
    # end value. com.oplus.camera.feature.integration.animation.SurfaceTransaction
    # defines setApply()V and setApply(I)V but NO getApply()I, so the framework logs
    #   W PropertyValuesHolder: Method getApply() with type null not found on target
    #   class ...SurfaceTransaction
    # and never drives the property -> setApply(int) is never called per frame ->
    # SurfaceControl$Transaction.apply() never fires during the animation -> the
    # reparented preview surface is left committed but un-animated and never restored
    # (rd/l.c() restore is gated on the animation completing) -> hang + next-capture
    # crash. Stock ships getApply() (the "apply" property is a frame-tick trigger: the
    # int is ignored, setApply(int)/setApply() both just call transaction.apply()), so
    # returning 0 is the correct OOS-baseline value, not a workaround.
    #
    # Anchored by the class signature + .source "SurfaceTransaction.java" (NOT an R8
    # name; this class keeps its real name), appended once. Idempotent.
    if tmp_dir is None:
        return

    class_sig = 'Lcom/oplus/camera/feature/integration/animation/SurfaceTransaction;'
    method = (
        '\n'
        '.method public getApply()I\n'
        '    .locals 1\n'
        '\n'
        '    const/4 v0, 0x0\n'
        '\n'
        '    return v0\n'
        '.end method\n'
    )

    for smali in Path(tmp_dir).glob('smali*/**/*.smali'):
        data = smali.read_text(encoding='utf-8')
        if f'.class public {class_sig}' not in data:
            continue
        if '.source "SurfaceTransaction.java"' not in data:
            continue
        if '.method public getApply()I' in data:
            continue  # already patched
        smali.write_text(data.rstrip('\n') + '\n' + method, encoding='utf-8')


def blob_fixup_oplus_camera_gallery_handoff(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    # Thumbnail tap -> open com.oneplus.gallery on the captured photo.
    #
    # On-device frida + static trace established the REAL tap path (an earlier
    # GalleryHelper-based attempt was dead code — the tap never enters GalleryHelper):
    #   thumbnail onClick -> CameraUIManager.P9(View,Uri,String,Bitmap,I,I,rm/e)V
    #   (the unique handler that logs "thumbnail_click").
    # P9 builds an intent (action = VIEW only if eo/t1.a else REVIEW; package = eo/t1.a())
    # but the launcher it calls (the 5-arg GalleryHelper.q) does NOT startActivity — it's a
    # MediaMetadataRetriever helper. On stock the actual "slide into gallery" is an
    # EMBEDDED INLINE render via the gallery-side SDK com.oplus.light.gallery.* / OliveView,
    # which is ABSENT on LOS — so there is NO startActivity path for the tap at all (frida
    # confirmed: tap fires neither GalleryHelper.g() nor any execStartActivity; it just
    # opens the in-app review overlay, which the getApply fix made render cleanly).
    #
    # True embedded parity needs a gallery-side SDK port (documented as the deep follow-up).
    # The achievable, reliable deliverable is a PLAIN full-screen launch: inject a
    # self-contained startActivity(ACTION_VIEW, data=capturedUri, type=mime,
    # setPackage("com.oneplus.gallery")) at P9's entry. com.oneplus.gallery /
    # com.oppo.gallery3d.app.ViewGallery is the confirmed VIEW image/* handler (REVIEW is
    # unregistered on this device).
    #
    # Switch: persist.sys.oplus.cam.plain_gallery (default TRUE = tap opens the gallery;
    # `setprop persist.sys.oplus.cam.plain_gallery false` falls back to the in-app review).
    # The swipe-up gesture (sd/d UpGestureDetector) review path is unaffected either way.
    #
    # Robustness: the patched class/method/field are all R8-obfuscated and differ across
    # apk copies, so EVERYTHING is read dynamically from the same smali at fixup time —
    # the file is found by .source "CameraUIManager.java"; P9 is the method whose body
    # contains "thumbnail_click"; the owner class and the Activity field (this.<f>) are
    # extracted from that file/method. A small static helper plainLaunchThumb(...)Z is
    # appended to the class and invoked at P9 entry; if it launched it returns-void early,
    # else P9 runs unchanged. Idempotent (skips if plainLaunchThumb already present).
    if tmp_dir is None:
        return

    method_re = re.compile(
        r'(?ms)^(\.method[^\n]*\n)(\s*\.(?:registers|locals) \d+\n)(.*?)^\.end method'
    )
    class_re = re.compile(r'^\.class[^\n]* (L[\w/$]+;)\s*$', re.MULTILINE)
    # Activity field read off `this` (v0 after the entry param-copy); fall back to any.
    act_v0_re = re.compile(r'iget-object \w+, v0, (L[\w/$]+;->\w+:Landroid/app/Activity;)')
    act_any_re = re.compile(r'(L[\w/$]+;->\w+:Landroid/app/Activity;)')

    for smali in Path(tmp_dir).glob('smali*/**/*.smali'):
        data = smali.read_text(encoding='utf-8')
        if '.source "CameraUIManager.java"' not in data:
            continue
        if 'plainLaunchThumb' in data:
            continue  # already patched
        cm = class_re.search(data)
        if not cm:
            continue
        cls = cm.group(1)  # e.g. Lmm/i0;

        # Locate P9 (the "thumbnail_click" handler) and extract the Activity field.
        act_field = None
        p9_match = None
        for m in method_re.finditer(data):
            if '"thumbnail_click"' in m.group(3):
                p9_match = m
                am = act_v0_re.search(m.group(3)) or act_any_re.search(m.group(3))
                if am:
                    act_field = am.group(1)
                break
        if p9_match is None or act_field is None:
            continue

        # P9 is .registers 25 -> params live in high registers (p0=v17, p2=v19, p3=v20).
        # A non-range invoke-static can only address v0..v15, so copy p0/p2/p3 into the
        # low locals v0/v1/v2 (move-object/from16 reaches high src) and invoke on those.
        # v0/v1/v2 are immediately re-initialised by P9's own param-copy prologue, so
        # clobbering them here is safe.
        entry_call = (
            '    move-object/from16 v0, p0\n'
            '\n'
            '    move-object/from16 v1, p2\n'
            '\n'
            '    move-object/from16 v2, p3\n'
            '\n'
            f'    invoke-static {{v0, v1, v2}}, {cls}->plainLaunchThumb({cls}Landroid/net/Uri;Ljava/lang/String;)Z\n'
            '\n'
            '    move-result v0\n'
            '\n'
            '    if-eqz v0, :cond_plain_thumb_off\n'
            '\n'
            '    return-void\n'
            '\n'
            '    :cond_plain_thumb_off\n'
        )

        helper = (
            '\n'
            f'.method public static plainLaunchThumb({cls}Landroid/net/Uri;Ljava/lang/String;)Z\n'
            '    .locals 3\n'
            '\n'
            '    const-string v0, "persist.sys.oplus.cam.plain_gallery"\n'
            '\n'
            '    const/4 v1, 0x1\n'
            '\n'
            '    invoke-static {v0, v1}, Landroid/os/SystemProperties;->getBoolean(Ljava/lang/String;Z)Z\n'
            '\n'
            '    move-result v0\n'
            '\n'
            '    if-nez v0, :do_launch\n'
            '\n'
            '    const/4 v0, 0x0\n'
            '\n'
            '    return v0\n'
            '\n'
            '    :do_launch\n'
            '    if-eqz p1, :no_launch\n'
            '\n'
            f'    iget-object v0, p0, {act_field}\n'
            '\n'
            '    if-eqz v0, :no_launch\n'
            '\n'
            '    new-instance v1, Landroid/content/Intent;\n'
            '\n'
            '    const-string v2, "android.intent.action.VIEW"\n'
            '\n'
            '    invoke-direct {v1, v2}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V\n'
            '\n'
            '    invoke-virtual {v1, p1, p2}, Landroid/content/Intent;->setDataAndType(Landroid/net/Uri;Ljava/lang/String;)Landroid/content/Intent;\n'
            '\n'
            '    const-string v2, "com.oneplus.gallery"\n'
            '\n'
            '    invoke-virtual {v1, v2}, Landroid/content/Intent;->setPackage(Ljava/lang/String;)Landroid/content/Intent;\n'
            '\n'
            '    const/4 v2, 0x1\n'
            '\n'
            '    invoke-virtual {v1, v2}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;\n'
            '\n'
            '    :try_start_0\n'
            '    invoke-virtual {v0, v1}, Landroid/app/Activity;->startActivity(Landroid/content/Intent;)V\n'
            '    :try_end_0\n'
            '    .catch Ljava/lang/Exception; {:try_start_0 .. :try_end_0} :catch_0\n'
            '\n'
            '    const/4 v0, 0x1\n'
            '\n'
            '    return v0\n'
            '\n'
            '    :catch_0\n'
            '    move-exception v1\n'
            '\n'
            '    const/4 v0, 0x0\n'
            '\n'
            '    return v0\n'
            '\n'
            '    :no_launch\n'
            '    const/4 v0, 0x0\n'
            '\n'
            '    return v0\n'
            '.end method\n'
        )

        # Insert the entry call right after P9's .registers/.locals directive.
        new_p9 = p9_match.group(1) + p9_match.group(2) + '\n' + entry_call + p9_match.group(3) + '.end method'
        data = data[:p9_match.start()] + new_p9 + data[p9_match.end():]
        # Append the helper to the class.
        data = data.rstrip('\n') + '\n' + helper
        smali.write_text(data, encoding='utf-8')


def blob_fixup_aiunit_authorize_camera(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    # AIUnit gates every client through AIUnitServiceBinder.authorize(ParamPackage):
    # it computes an "authorized" boolean in v9, and if v9 == 0 returns
    # kErrorAuthorizeFail. On stock the calling package is trusted via the Oplus
    # security framework (com.oplus.permission.safe.* + signature checks) that LOS
    # does not have, so OplusCamera / the gallery never pass authorize and the AI
    # engine refuses them. Whitelist our two first-party clients by name: right
    # after v9 is finalised (the unique `:goto_2` + StringBuilder log site), force
    # v9 = 1 when the calling package (v5) is com.oplus.camera or com.oneplus.gallery.
    #
    # Re-anchored for the .201 dump: the authorize method now keeps the auth flag in
    # v9 (old fork keyed v5/v6 + a `:goto_3` + StringBuilder site that no longer
    # exists). v9 is overwritten by the StringBuilder logging path immediately after,
    # and v10 is reused as the StringBuilder, so borrowing v10 as the areEqual scratch
    # is safe (it is re-defined by `new-instance v10` on the next line).
    if tmp_dir is None:
        return

    smali = Path(tmp_dir) / 'smali_classes2/com/oplus/aiunit/core/AIUnitServiceBinder.smali'
    if not smali.exists():
        return
    data = smali.read_text(encoding='utf-8')
    old = (
        '    :goto_2\n'
        '    new-instance v10, Ljava/lang/StringBuilder;\n'
    )
    new = (
        '    :goto_2\n'
        '    const-string v10, "com.oplus.camera"\n'
        '\n'
        '    invoke-static {v5, v10}, Lkotlin/jvm/internal/Intrinsics;->areEqual(Ljava/lang/Object;Ljava/lang/Object;)Z\n'
        '\n'
        '    move-result v10\n'
        '\n'
        '    if-nez v10, :cond_oplus_aiunit_trusted_auth\n'
        '\n'
        '    const-string v10, "com.oneplus.gallery"\n'
        '\n'
        '    invoke-static {v5, v10}, Lkotlin/jvm/internal/Intrinsics;->areEqual(Ljava/lang/Object;Ljava/lang/Object;)Z\n'
        '\n'
        '    move-result v10\n'
        '\n'
        '    if-eqz v10, :cond_oplus_aiunit_auth\n'
        '\n'
        '    :cond_oplus_aiunit_trusted_auth\n'
        '    const/4 v9, 0x1\n'
        '\n'
        '    :cond_oplus_aiunit_auth\n'
        '    new-instance v10, Ljava/lang/StringBuilder;\n'
    )
    fixed = data.replace(old, new, 1)
    if fixed != data:
        smali.write_text(fixed, encoding='utf-8')

    # AIUnitProvider gates ContentProvider clients through e() (authorizeByRemote),
    # which reads the caller's com.oplus.aiunit.auth_style <meta-data> and returns a
    # boolean. The gallery AI lane (#5) reaches AIUnit through this provider, so
    # whitelist com.oplus.camera + com.oneplus.gallery here too: right after the
    # non-null packageName guard (:cond_0), return true for either package. p0 is the
    # provider `this`, returned as the Z result in the trusted branch (which ends in
    # return, so reusing it is safe); v1 is the next-defined Context scratch in the
    # fall-through path, so borrowing it for the areEqual result is safe.
    provider = Path(tmp_dir) / 'smali_classes2/com/oplus/aiunit/AIUnitProvider.smali'
    if provider.exists():
        pdata = provider.read_text(encoding='utf-8')
        pold = (
            '    :cond_0\n'
            '    invoke-virtual {p0}, Lcom/oplus/aiunit/base/component/BaseContentProvider;->a()Landroid/content/Context;\n'
        )
        pnew = (
            '    :cond_0\n'
            '    const-string v1, "com.oplus.camera"\n'
            '\n'
            '    invoke-static {v0, v1}, Lkotlin/jvm/internal/Intrinsics;->areEqual(Ljava/lang/Object;Ljava/lang/Object;)Z\n'
            '\n'
            '    move-result v1\n'
            '\n'
            '    if-nez v1, :cond_oplus_aiunit_provider_trusted\n'
            '\n'
            '    const-string v1, "com.oneplus.gallery"\n'
            '\n'
            '    invoke-static {v0, v1}, Lkotlin/jvm/internal/Intrinsics;->areEqual(Ljava/lang/Object;Ljava/lang/Object;)Z\n'
            '\n'
            '    move-result v1\n'
            '\n'
            '    if-eqz v1, :cond_oplus_aiunit_provider_check\n'
            '\n'
            '    :cond_oplus_aiunit_provider_trusted\n'
            '    const/4 p0, 0x1\n'
            '\n'
            '    return p0\n'
            '\n'
            '    :cond_oplus_aiunit_provider_check\n'
            '    invoke-virtual {p0}, Lcom/oplus/aiunit/base/component/BaseContentProvider;->a()Landroid/content/Context;\n'
        )
        pfixed = pdata.replace(pold, pnew, 1)
        if pfixed != pdata:
            provider.write_text(pfixed, encoding='utf-8')


def blob_fixup_aiunit_plugin_so_permissions(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    # AIUnit downloads editor plugins and unzips their JNI .so into its app-data dir
    # (FileUtil.unzipSoFromPlugin), then System.load()s them. The unzip preserves the
    # zip entry's mode, which leaves the extracted .so non-executable on LOS, so the
    # subsequent load fails. Force the extracted file (v10) readable + executable right
    # after the unzip call. The owner-only single-arg overloads suffice (AIUnit owns
    # its plugin dir); v9 is dead between the unzip and the following `const/4 v9, 0x0`
    # (it is re-defined there), so it is a verifier-safe scratch for the `true` const.
    #
    # Re-anchored for the .201 dump: FileUtil moved from com/oplus/orange/core/utils to
    # com/oplus/orange/utils, and the .so path is now unzipSoFromPlugin (the hash-file
    # unzip is a separate method) — anchored on the {v2,v9,v10} unzip call site.
    if tmp_dir is None:
        return

    smali = Path(tmp_dir) / 'smali_classes2/com/oplus/orange/utils/FileUtil.smali'
    if not smali.exists():
        return
    data = smali.read_text(encoding='utf-8')
    old = (
        '    invoke-static {v2, v9, v10}, Lcom/oplus/orange/utils/FileUtil;->unzip(Ljava/util/zip/ZipFile;Ljava/util/zip/ZipEntry;Ljava/io/File;)V\n'
        '\n'
        '    .line 218\n'
        '    .line 219\n'
        '    .line 220\n'
        '    const/4 v9, 0x0\n'
    )
    new = (
        '    invoke-static {v2, v9, v10}, Lcom/oplus/orange/utils/FileUtil;->unzip(Ljava/util/zip/ZipFile;Ljava/util/zip/ZipEntry;Ljava/io/File;)V\n'
        '\n'
        '    const/4 v9, 0x1\n'
        '\n'
        '    invoke-virtual {v10, v9}, Ljava/io/File;->setReadable(Z)Z\n'
        '\n'
        '    invoke-virtual {v10, v9}, Ljava/io/File;->setExecutable(Z)Z\n'
        '\n'
        '    .line 218\n'
        '    .line 219\n'
        '    .line 220\n'
        '    const/4 v9, 0x0\n'
    )
    fixed = data.replace(old, new, 1)
    if fixed != data:
        smali.write_text(fixed, encoding='utf-8')


def blob_fixup_oppogallery_op15_native_libs(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    # OppoGallery2's ODNN retouch (AI eraser etc.) declares + dlopens the QNN HTP
    # runtime. The .201 apk still ships the V75/aiboost manifest entries, but SM8850
    # .201 has NO /odm/lib64/aiboost dir — the QNN runtime is the V81 set, flat in
    # /odm/lib64. Rewrite the manifest V75/aiboost uses-native-library block to the
    # V81 flat names, and bake the 6 V81 libs (sourced into configs/lib64 from the
    # dump's odm/lib64) into the apk's own lib/arm64-v8a so the gallery loads them by
    # basename from its nativeLibraryDir on LOS. Ported verbatim from the koaaN fork
    # (re-anchored: the .201 aiboost block matches the old `old` list).
    if tmp_dir is None:
        return

    manifest = Path(tmp_dir) / 'AndroidManifest.xml'
    data = manifest.read_text(encoding='utf-8') if manifest.exists() else ''
    old = [
        '        <uses-native-library android:name="/odm/lib64/aiboost/libaiboost.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/aiboost/libaiboost_qnn_external_delegate.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/aiboost/libQnnHtp.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/aiboost/libQnnHtpPrepare.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/aiboost/libQnnHtpV75Stub.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/aiboost/libQnnSystem.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/aiboost/libtransformer_lite.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/Skel_signed/aiboost/libQnnHtpV75Skel.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/aiboost/Skel_unsigned/libQnnHtpV75Skel.so" android:required="false"/>\n',
    ]
    new = [
        '        <uses-native-library android:name="/odm/lib64/libQnnHtp.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/libQnnHtpPrepare.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/libQnnHtpV81Stub.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/libQnnHtpV81CalculatorStub.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/libQnnSaver.so" android:required="false"/>\n',
        '        <uses-native-library android:name="/odm/lib64/libQnnSystem.so" android:required="false"/>\n',
    ]

    fixed = data
    anchor = ''.join(line for line in old if line in fixed)
    if anchor:
        fixed = fixed.replace(anchor, ''.join(new))
    elif new[-1] not in fixed:
        insert_after = '        <uses-native-library android:name="libOpenCL.so" android:required="true"/>\n'
        fixed = fixed.replace(insert_after, insert_after + ''.join(new))

    if fixed != data:
        manifest.write_text(fixed, encoding='utf-8')

    lib_dir = Path(tmp_dir) / 'lib/arm64-v8a'
    lib_dir.mkdir(parents=True, exist_ok=True)
    source_dir = Path(__file__).resolve().parent / 'configs/lib64'
    for lib in (
        'libQnnHtp.so',
        'libQnnHtpPrepare.so',
        'libQnnHtpV81Stub.so',
        'libQnnHtpV81CalculatorStub.so',
        'libQnnSaver.so',
        'libQnnSystem.so',
    ):
        shutil.copy2(source_dir / lib, lib_dir / lib)


def blob_fixup_oppogallery_receiver_flags(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    # A14+ requires every Context.registerReceiver for a non-system broadcast to
    # pass RECEIVER_EXPORTED or RECEIVER_NOT_EXPORTED, else SecurityException crashes
    # the app on A16. Force RECEIVER_NOT_EXPORTED (clear 0x2, set 0x4) on the gallery's
    # AIUnit-vision broadcast manager. Re-anchored for .201: the receiver class moved
    # from smali_classes8/.../ey.smali (koaaN, CPH2745) to smali_classes8/.../h14.smali,
    # which has 3 registerReceiver(...Handler;I) call sites — site 1 keeps the flags in
    # v9, sites 2+3 in v7.
    if tmp_dir is None:
        return

    smali = Path(tmp_dir) / 'smali_classes8/com/oplus/aiunit/vision/h14.smali'
    if not smali.exists():
        return
    data = smali.read_text(encoding='utf-8')
    fixed = data
    # Site 1: flags in v9 (invoke-virtual/range {v4 .. v9}).
    fixed = fixed.replace(
        '    move v9, p2\n'
        '\n'
        '    .line 275\n'
        '    invoke-virtual/range {v4 .. v9}, Landroid/content/Context;->registerReceiver(Landroid/content/BroadcastReceiver;Landroid/content/IntentFilter;Ljava/lang/String;Landroid/os/Handler;I)Landroid/content/Intent;\n',
        '    move v9, p2\n'
        '\n'
        '    and-int/lit8 v9, v9, -0x3\n'
        '\n'
        '    or-int/lit8 v9, v9, 0x4\n'
        '\n'
        '    .line 275\n'
        '    invoke-virtual/range {v4 .. v9}, Landroid/content/Context;->registerReceiver(Landroid/content/BroadcastReceiver;Landroid/content/IntentFilter;Ljava/lang/String;Landroid/os/Handler;I)Landroid/content/Intent;\n',
        1,
    )
    # Sites 2 + 3: flags in v7 (invoke-virtual/range {v2 .. v7}); identical, patch both.
    fixed = fixed.replace(
        '    invoke-virtual/range {v2 .. v7}, Landroid/content/Context;->registerReceiver(Landroid/content/BroadcastReceiver;Landroid/content/IntentFilter;Ljava/lang/String;Landroid/os/Handler;I)Landroid/content/Intent;\n',
        '    and-int/lit8 v7, v7, -0x3\n'
        '\n'
        '    or-int/lit8 v7, v7, 0x4\n'
        '\n'
        '    invoke-virtual/range {v2 .. v7}, Landroid/content/Context;->registerReceiver(Landroid/content/BroadcastReceiver;Landroid/content/IntentFilter;Ljava/lang/String;Landroid/os/Handler;I)Landroid/content/Intent;\n',
    )
    if fixed != data:
        smali.write_text(fixed, encoding='utf-8')


def blob_fixup_oppogallery_safe_box(ctx, file, file_path, *args, tmp_dir=None, **kwargs):
    # The gallery's feature-support query (hag.h(q26;Z)Boolean, a big sswitch over
    # feature keys) resolves "feature_is_support_user_custom_safe_box" via hag.a1(),
    # which reads an Oplus config absent on LOS and crashes the SafeBox path. Force the
    # SafeBox-support case to return true (RESTORE stock behaviour). Re-anchored for
    # .201: koaaN keyed mn4.f(String;ZZ)Z; the .201 class is
    # smali_classes7/.../hag.smali (the safe_box key constant + the :cond_4b a1() check
    # are the stable anchor — obfuscated class names drift, the feature-key string does
    # not).
    if tmp_dir is None:
        return

    smali = Path(tmp_dir) / 'smali_classes7/com/oplus/aiunit/vision/hag.smali'
    if not smali.exists():
        return
    data = smali.read_text(encoding='utf-8')
    old = (
        '    :cond_4b\n'
        '    invoke-virtual {p0}, Lcom/oplus/aiunit/vision/hag;->a1()Z\n'
        '\n'
        '    move-result p0\n'
        '\n'
        '    xor-int/2addr p0, v8\n'
        '\n'
        '    invoke-static {p0}, Ljava/lang/Boolean;->valueOf(Z)Ljava/lang/Boolean;\n'
    )
    new = (
        '    :cond_4b\n'
        '    const/4 p0, 0x1\n'
        '\n'
        '    invoke-static {p0}, Ljava/lang/Boolean;->valueOf(Z)Ljava/lang/Boolean;\n'
    )
    fixed = data.replace(old, new, 1)
    if fixed != data:
        smali.write_text(fixed, encoding='utf-8')


# Blob fixups port (restored from the proven dirtyaf fork vendor_oplus_camera,
# branch lineage-23.2-camera). LOS lacks the OnePlus/Oplus framework, so these
# app-side shims let OplusCamera + the OCS SDK jars RUN and reach capture. They
# are app-RUNTIME co-requisites, NOT the capture lever itself (identity stamp +
# libalogencrypt + oemlayer + quickjpeg=0 + geometry, handled elsewhere).
#
# Static git patches (patches/) carry the fingerprint-anchored IS_OPLUS_PACKAGE
# identity stamp (BaseMode, jar); the programmatic .call() fixups carry the broad,
# content-addressed transforms (the TypeFaceUtil/OplusExtraConfiguration default-font
# gut-replace, vendor-tag renames, wrapper-class rewrites, SystemProperties rewrite,
# manifest <uses-library>/permission edits) that cannot be expressed as line-anchored
# diffs and would break under apktool re-obfuscation.
#
# Apply order per artifact: apktool unpack -> static patch_dir (anchored to the
# pristine smali) -> programmatic transforms -> repack -> stripzip.
blob_fixups: blob_fixups_user_type = {
    'system_ext/framework/com.oplus.camera.unit.sdk.jar': blob_fixup()
        .call(blob_fixup_apktool_unpack_src)
        .patch_dir('patches')
        .call(blob_fixup_oplus_camera_framework_shims)
        .apktool_pack()
        .stripzip(),
    'system_ext/framework/com.oplus.camera.unit.sdk.adapter.jar': blob_fixup()
        .call(blob_fixup_apktool_unpack_src)
        .call(blob_fixup_oplus_camera_framework_shims)
        .apktool_pack()
        .stripzip(),
    'system_ext/priv-app/OplusCamera/OplusCamera.apk': blob_fixup()
        # --no-res: keep resources.arsc raw (faithful locale/AE-HDR config + stable resource
        # IDs); smali is still decoded for the dex fixups; manifest stays binary and is
        # patched via pyaxml in blob_fixup_opluscamera_manifest_axml.
        .call(blob_fixup_apktool_unpack_src)
        .call(blob_fixup_opluscamera_manifest_axml)
        .call(blob_fixup_oplus_camera_system_properties)
        .call(blob_fixup_oplus_camera_framework_shims)
        .call(blob_fixup_oplus_camera_typeface_default)
        .call(blob_fixup_oplus_camera_blur_npe_guard)
        .call(blob_fixup_oplus_camera_surface_transaction_getapply)
        .call(blob_fixup_oplus_camera_gallery_handoff)
        .apktool_pack()
        .stripzip(),
    'system_ext/priv-app/AIUnit/AIUnit.apk': blob_fixup()
        .call(blob_fixup_apktool_unpack_src)
        .call(blob_fixup_aiunit_authorize_camera)
        .call(blob_fixup_aiunit_plugin_so_permissions)
        .call(blob_fixup_oplus_camera_framework_shims)
        .apktool_pack()
        .stripzip(),
    'system_ext/priv-app/OppoGallery2/OppoGallery2.apk': blob_fixup()
        .call(blob_fixup_apktool_unpack_full)
        .call(blob_fixup_opluscamera_uses_library)
        .call(blob_fixup_oppogallery_op15_native_libs)
        .call(blob_fixup_oppogallery_receiver_flags)
        .call(blob_fixup_oppogallery_safe_box)
        .apktool_pack()
        .stripzip(),
}  # fmt: skip

namespace_imports = [
    'vendor/oplus/proprietary_vendor_oplus_camera-sm8850/camera',
    'vendor/oneplus/infiniti',
    'vendor/oneplus/sm8850-common',
    'hardware/oplus',
]

# LOS-standard source/generated split:
#   - SOURCE repo (this dir, vendor/oplus/camera-sm8850): extract-files.py,
#     proprietary-files.txt, patches/, sepolicy/,
#     oplus-camera-stubs/, configs/, opluscamera.mk, SEPolicy.mk. The patch&pin
#     layer; device_path/patch_dir resolve here (BlobFixupCtx(self.device_path)).
#   - GENERATED repo (vendor/oplus/proprietary_vendor_oplus_camera-sm8850): the
#     raw extracted blobs (camera/proprietary/**) + extract_utils-generated
#     camera/{Android.bp,Android.mk,camera-vendor.mk,BoardConfigVendor.mk}.
# vendor_rel_path = 'vendor/<vendor>/<device>' = the generated mount path; the
# 'camera' device sub-dir keeps the generated filenames (camera-vendor.mk) and
# the camera/proprietary/ layout identical. device_rel_path stays the source
# repo so proprietary-files.txt + patches/ resolve from here unchanged.
module = ExtractUtilsModule(
    'camera',
    'oplus/proprietary_vendor_oplus_camera-sm8850',
    device_rel_path='vendor/oplus/camera-sm8850',
    blob_fixups=blob_fixups,
    lib_fixups=lib_fixups,
    namespace_imports=namespace_imports,
)

if __name__ == '__main__':
    utils = ExtractUtils.device(module)
    utils.run()
