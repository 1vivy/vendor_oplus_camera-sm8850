package android.content.pm;

import android.content.Context;

/** Stub for OEM package manager. OplusCamera obtains it via getOplusPackageManager(Context). No-op. */
public class OplusPackageManager {
    private static final OplusPackageManager INSTANCE = new OplusPackageManager();

    public static OplusPackageManager getOplusPackageManager(Context context) {
        return INSTANCE;
    }
}
