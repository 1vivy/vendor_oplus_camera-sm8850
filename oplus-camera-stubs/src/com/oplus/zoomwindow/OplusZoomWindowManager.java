package com.oplus.zoomwindow;

public class OplusZoomWindowManager {
    private static final OplusZoomWindowManager INSTANCE = new OplusZoomWindowManager();

    public static OplusZoomWindowManager getInstance() {
        return INSTANCE;
    }

    public OplusZoomWindowInfo getCurrentZoomWindowState() {
        return new OplusZoomWindowInfo();
    }

    public boolean isSupportZoomWindowMode() {
        return false;
    }

    public boolean isSupportZoomMode(String pkg, int userId, String caller, android.os.Bundle extras) {
        return false;
    }

    public int startZoomWindow(android.content.Intent intent, android.os.Bundle options, int userId, String caller) {
        return -1;
    }

    public boolean registerZoomWindowObserver(IOplusZoomWindowObserver observer) {
        return true;
    }

    public boolean unregisterZoomWindowObserver(IOplusZoomWindowObserver observer) {
        return true;
    }
}
