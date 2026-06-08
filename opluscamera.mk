# Blob dependencies
PRODUCT_PACKAGES += \
    android.hardware.graphics.common-V3-ndk.vendor

# APS P010 plane-layout fix: first-party GOT-interposer shim (apsfixup/), installed to
# /odm/lib64 and DT_NEEDED-injected into odm/lib64/libAlgoProcess.so via
# device/oneplus/infiniti/extract-files.py (.add_needed) + exposed in
# vendor/etc/public.libraries.txt via device/oneplus/sm8850-common/extract-files.py. Replaces
# the fragile binary min()/described-height geometry patch (kept as fallback until the shim is
# device-validated). See apsfixup/docs/PORTING.md.
PRODUCT_PACKAGES += \
    libapsfixup

# Framework
# PRODUCT_BOOT_JARS += \
#    oplus-framework

# OPlus camera framework wrapper stubs (com.oplus.wrapper.*, OplusHeifWriter, etc.).
# Shipped as a regular system_ext/framework shared library (NOT a boot jar) and
# pulled into OplusCamera's classloader via <uses-library oplus.camera.stubs>
# (declared in privapp-permissions-oplus.xml, injected into the app manifest by
# blob_fixup_opluscamera_uses_library in extract-files.py). Keeping it OFF
# PRODUCT_BOOT_JARS avoids baking app-only stubs into boot.art and scopes the
# wrapper classes to just the app that needs them.
PRODUCT_PACKAGES += \
    oplus-camera-stubs

# Init
#PRODUCT_PACKAGES += \
#    init.oplus.camera.rc

# Permissions
PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/configs/permissions/com.oplus.android-features.xml:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/permissions/com.oplus.android-features.xml \
    $(LOCAL_PATH)/configs/permissions/oplus_google_lens_config.xml:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/permissions/oplus_google_lens_config.xml \
    $(LOCAL_PATH)/configs/permissions/privapp-permissions-oplus.xml:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/permissions/privapp-permissions-oplus.xml \
    $(LOCAL_PATH)/configs/sysconfig/hiddenapi-package-oplus-whitelist.xml:$(TARGET_COPY_OUT_SYSTEM)/etc/sysconfig/hiddenapi-package-oplus-whitelist.xml

# Properties
PRODUCT_PRODUCT_PROPERTIES += \
    persist.vendor.camera.privapp.list=com.oplus.camera,com.oneplus.gallery \
    ro.com.google.lens.oem_camera_package=com.oplus.camera \
    ro.com.google.lens.oem_image_package=com.oneplus.gallery,com.oplus.screenshot \
    ro.oplus.camera.defercap.support=1 \
    ro.oplus.system.camera.name=com.oplus.camera \
    ro.oplus.camera.defercap.all.quick.visible.support=1 \
    ro.oplus.camera.livephoto.support=1 \
    ro.camera.disableHeicUltraHDR=1 \
    oplus.software.camera.10bit=1 \
    vendor.camera.aux.packagelist=com.oplus.camera \
    ro.oplus.camera.facing.front.need.disable.nfc=1 \
    ro.oplus.camera.portrait.center.switch=oplus.switch.portrait.center \
    ro.oplus.camera.portrait_center.prefix=oplus.portrait.center. \
    ro.oplus.camera.video.beauty.switch=oplus.switch.video.beauty \
    ro.oplus.camera.video_beauty.prefix=oplus.video.beauty. \
    ro.oplus.camera.speechassist=true \
    ro.oplus.system.camera.flashlight=com.oplus.motor.flashlight \
    ro.camera.privileged.3rdpartyApp=com.mediatek.expert.mtkcamhelper;com.aiunit.aon; \
    persist.logd.log.load.camerahalserver.lower_limit=1000 \
    persist.logd.log.load.camerahalserver.threshold=800000 \
    persist.logd.log.load.camerahalserver.upper_limit=3000 \
    persist.logd.log.load.com.oplus.camera.lower_limit=1000 \
    persist.logd.log.load.com.oplus.camera.threshold=800000 \
    persist.logd.log.load.com.oplus.camera.upper_limit=3000 \
    persist.logd.log.load.vendor.qti.camera.provider-service_64.lower_limit=500 \
    persist.logd.log.load.vendor.qti.camera.provider-service_64.threshold=400000 \
    persist.logd.log.load.vendor.qti.camera.provider-service_64.upper_limit=1500 \

# Photo
$(call soong_config_set,camera,package_name,com.oplus.packageName)

# Video
$(call soong_config_set_bool,camera,override_format_from_reserved,true)

# SEpolicy
include vendor/oplus/camera-sm8850/sepolicy/SEPolicy.mk

# Inherit from camera-vendor.mk (generated blobs now live in the split repo
# vendor/oplus/proprietary_vendor_oplus_camera-sm8850; this source repo keeps
# only the patch&pin layer + opluscamera.mk + sepolicy).
$(call inherit-product, vendor/oplus/proprietary_vendor_oplus_camera-sm8850/camera/camera-vendor.mk)
