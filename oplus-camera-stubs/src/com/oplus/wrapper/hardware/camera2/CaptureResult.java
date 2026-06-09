// MANUAL-STUB: needed for IPU SDK classloader.
// LOS port: getNativeMetadata() must return the result's REAL native metadata (not null) so
// SuperEIS / motion-photo can read camera metadata via the native ptr. AOSP CaptureResult holds
// `private final CameraMetadataNative mResults`; we wrap that real object (it stays valid as long
// as the underlying CaptureResult is alive, matching the real OPlus wrapper's semantics). Stub
// builds with platform_apis:true; OplusCamera is hidden-API-exempt at runtime.
package com.oplus.wrapper.hardware.camera2;

public class CaptureResult {
    private final android.hardware.camera2.CaptureResult mResult;

    public CaptureResult() {
        mResult = null;
    }

    public CaptureResult(android.hardware.camera2.CaptureResult r) {
        mResult = r;
    }

    public com.oplus.wrapper.hardware.camera2.impl.CameraMetadataNative getNativeMetadata() {
        if (mResult == null) {
            return null;
        }
        try {
            java.lang.reflect.Field f =
                    android.hardware.camera2.CaptureResult.class.getDeclaredField("mResults");
            f.setAccessible(true);
            android.hardware.camera2.impl.CameraMetadataNative impl =
                    (android.hardware.camera2.impl.CameraMetadataNative) f.get(mResult);
            if (impl == null) {
                return null;
            }
            return new com.oplus.wrapper.hardware.camera2.impl.CameraMetadataNative(impl);
        } catch (Throwable t) {
            return null;
        }
    }
}
