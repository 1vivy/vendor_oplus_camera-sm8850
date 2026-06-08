package com.oplus.osense.eventinfo;

import android.os.Bundle;
import android.os.Parcel;
import android.os.Parcelable;

public class OsenseConfig implements Parcelable {
    public static final Parcelable.Creator<OsenseConfig> CREATOR = new Parcelable.Creator<OsenseConfig>() {
        @Override
        public OsenseConfig createFromParcel(Parcel in) {
            return new OsenseConfig(in);
        }

        @Override
        public OsenseConfig[] newArray(int size) {
            return new OsenseConfig[size];
        }
    };

    private int mEventType;
    private Bundle mExtra;

    public OsenseConfig(Parcel in) {
    }

    public OsenseConfig(int eventType, Bundle extra) {
        this.mEventType = eventType;
        this.mExtra = extra;
    }

    public int getEventType() {
        return mEventType;
    }

    public Bundle getExtra() {
        return mExtra;
    }

    @Override
    public int describeContents() {
        return 0;
    }

    @Override
    public void writeToParcel(Parcel dest, int flags) {
    }
}
