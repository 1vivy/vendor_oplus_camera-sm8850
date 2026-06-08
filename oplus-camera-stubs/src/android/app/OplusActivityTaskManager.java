package android.app;

import android.content.ComponentName;

/**
 * Stub for the OEM activity-task manager. OplusCamera queries
 * getInstance().getTopActivityComponentName() (e.g. to detect what launched it / multi-window
 * state). On stock this is in oplus-framework.jar (bootclasspath); shipped here via
 * oplus.camera.stubs. No-op: report no known top activity (callers null-check).
 */
public class OplusActivityTaskManager {

    private static final OplusActivityTaskManager INSTANCE = new OplusActivityTaskManager();

    public static OplusActivityTaskManager getInstance() {
        return INSTANCE;
    }

    public ComponentName getTopActivityComponentName() {
        return null;
    }
}
