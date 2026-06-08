package com.oplus.uah.info;

import java.util.ArrayList;

public class UAHEventRequest {
    private int mEventId;
    private String mSceneName;
    private int mTimeout;
    private ArrayList mList;

    public UAHEventRequest(int eventId, String sceneName, int timeout, ArrayList list) {
        this.mEventId = eventId;
        this.mSceneName = sceneName;
        this.mTimeout = timeout;
        this.mList = list;
    }

    public int getEventId() {
        return mEventId;
    }

    public String getSceneName() {
        return mSceneName;
    }

    public int getTimeout() {
        return mTimeout;
    }

    public ArrayList getList() {
        return mList;
    }
}
