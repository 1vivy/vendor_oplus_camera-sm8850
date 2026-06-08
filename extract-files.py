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
    # The com.oplus.wrapper.* / OplusHeifWriter classes the app references live in
    # oplus-framework.jar (BOOTCLASSPATH) on stock. We ship them instead as the
    # off-bootclasspath shared library "oplus.camera.stubs" (oplus-camera-stubs.jar in
    # /system_ext/framework, declared in privapp-permissions-oplus.xml). For the app's
    # own classloader to resolve them, the app must declare <uses-library> for it.
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
        .call(blob_fixup_apktool_unpack_full)
        .call(blob_fixup_opluscamera_oppo_component_safe)
        .call(blob_fixup_opluscamera_uses_library)
        .call(blob_fixup_oplus_camera_system_properties)
        .call(blob_fixup_oplus_camera_framework_shims)
        .apktool_pack()
        .stripzip(),
    'system_ext/priv-app/AIUnit/AIUnit.apk': blob_fixup()
        .call(blob_fixup_apktool_unpack_src)
        .call(blob_fixup_aiunit_authorize_camera)
        .call(blob_fixup_aiunit_plugin_so_permissions)
        .call(blob_fixup_oplus_camera_framework_shims)
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
