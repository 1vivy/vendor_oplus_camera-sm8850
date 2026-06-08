package com.oplus.uah;

import com.oplus.uah.info.UAHEventRequest;

public class UAHResClient {
    public static UAHResClient get(Class cls) {
        return new UAHResClient();
    }

    public int acquireEvent(UAHEventRequest mUahEventRequest) {
        return 0;
    }

    public void release(int handle) {
    }

    public int getModeStatus(int mode) {
        return 0;
    }

    public String getResState(int opCode) {
        return null;
    }
}
