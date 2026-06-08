package com.oplus.flexiblewindow;

import android.app.Activity;

public class FlexibleWindowManager {
    public static final int FLEXIBLE_WINDOW_EMBEDDED_MODE = 3;
    public static final int FLEXIBLE_WINDOW_FREEFORM_MODE = 1;
    public static final int FLEXIBLE_WINDOW_INSENSIBLE_MODE = 4;
    public static final int FLEXIBLE_WINDOW_INVALID_MODE = -1;
    public static final int FLEXIBLE_WINDOW_SPLIT_SCREEN_MODE = 2;

    private static volatile FlexibleWindowManager sInstance;

    private FlexibleWindowManager() {
    }

    public static FlexibleWindowManager getInstance() {
        if (sInstance == null) {
            synchronized (FlexibleWindowManager.class) {
                if (sInstance == null) {
                    sInstance = new FlexibleWindowManager();
                }
            }
        }
        return sInstance;
    }

    public int getFlexibleWindowState(Activity activity) {
        return -1;
    }

    public void removeEmbeddedContainerTask(int embeddedTaskId, int containerTaskId) {
    }
}
