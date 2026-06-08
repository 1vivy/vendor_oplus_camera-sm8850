package com.oplus.osense.eventinfo;

import android.os.Bundle;
import android.os.Parcel;
import android.os.Parcelable;

public class OsenseEventResult implements Parcelable {
    public static final Parcelable.Creator<OsenseEventResult> CREATOR = new Parcelable.Creator<OsenseEventResult>() {
        @Override
        public OsenseEventResult createFromParcel(Parcel in) {
            return new OsenseEventResult(in);
        }

        @Override
        public OsenseEventResult[] newArray(int size) {
            return new OsenseEventResult[size];
        }
    };

    private int mEventType;
    private int mEventStateType;
    private Bundle mExtraData;

    public OsenseEventResult(Parcel in) {
    }

    public OsenseEventResult(int eventType, int eventStateType, Bundle bundle) {
        this.mEventType = eventType;
        this.mEventStateType = eventStateType;
        this.mExtraData = bundle;
    }

    public int getEventType() {
        return mEventType;
    }

    public int getEventStateType() {
        return mEventStateType;
    }

    public Bundle getExtraData() {
        return mExtraData;
    }

    @Override
    public int describeContents() {
        return 0;
    }

    @Override
    public void writeToParcel(Parcel dest, int flags) {
    }
}
