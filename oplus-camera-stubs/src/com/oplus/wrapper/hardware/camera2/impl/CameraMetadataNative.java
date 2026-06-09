// MANUAL-STUB: needed for IPU SDK classloader.
// LOS port: this wrapper must DELEGATE to the real hidden
// android.hardware.camera2.impl.CameraMetadataNative so SuperEIS / motion-photo
// (ApsUtils.getMetadataPtrForJni -> CaptureResult.getNativeMetadata -> getMetadataPtr) gets a
// real native metadata pointer instead of 0/null. The stub builds with platform_apis:true and
// OplusCamera is a hidden-API-exempt priv-app, so getMetadataPtr() (public @hide) is callable.
package com.oplus.wrapper.hardware.camera2.impl;

public class CameraMetadataNative {
    private final android.hardware.camera2.impl.CameraMetadataNative mImpl;

    public CameraMetadataNative() {
        mImpl = null;
    }

    public CameraMetadataNative(android.hardware.camera2.impl.CameraMetadataNative impl) {
        mImpl = impl;
    }

    public long getMetadataPtr() {
        return mImpl == null ? 0L : mImpl.getMetadataPtr();
    }
}
