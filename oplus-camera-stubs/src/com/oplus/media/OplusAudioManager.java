package com.oplus.media;

public class OplusAudioManager {
    private static final class InstanceHolder {
        private static final OplusAudioManager INSTANCE = new OplusAudioManager();
    }

    private OplusAudioManager() {
    }

    public static OplusAudioManager getInstance() {
        return InstanceHolder.INSTANCE;
    }

    public void setRingerModeInternal(int ringerMode) {
    }
}
