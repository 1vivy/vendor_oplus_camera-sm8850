package android.os.customize;

import android.content.Context;

/** Stub for OEM MDM restriction manager. OplusCamera checks screen-record forbid state. No-op. */
public class OplusCustomizeRestrictionManager {
    private static final OplusCustomizeRestrictionManager INSTANCE = new OplusCustomizeRestrictionManager();

    public static OplusCustomizeRestrictionManager getInstance(Context context) {
        return INSTANCE;
    }

    public boolean getForbidRecordScreenState() {
        return false;
    }
}
