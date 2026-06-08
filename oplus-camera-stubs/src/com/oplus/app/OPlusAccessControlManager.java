package com.oplus.app;

import java.util.List;
import java.util.Map;

public class OPlusAccessControlManager {
    public static final String ACCESS_CONTROL_FROM_CONTAINER = "Access_Control_From_Container";
    public static final String ACCESS_CONTROL_FROM_CONTAINER_FOR_CONTAINER_TASKID = "embeddedContainerTaskId";
    public static final String ACCESS_CONTROL_FROM_POCKET_STUDIO = "Access_Control_From_Pocket_Studio";
    public static final String ACCESS_CONTROL_FROM_RECENT_TASK_TO_SPLIT_SCREEN = "Access_Control_From_Recent_Task_To_Split_Screen";
    public static final String ACCESS_CONTROL_LOCK_ENABLED = "access_control_lock_enabled";
    public static final String ACCESS_CONTROL_LOCK_MODE = "access_control_lock_mode";
    public static final String ACCESS_CONTROL_PACKAGES_LIST_FROM_POCKET_STUDIO = "Access_Control_Packages_From_Pocket_Studio";
    public static final String ACCESS_CONTROL_PACKAGE_NAME = "Access_Control_Package_Name";
    public static final String ACCESS_CONTROL_PACKAGE_USERID = "Access_Control_Package_UserId";
    public static final String ACCESS_CONTROL_USER_ID_LIST_FROM_POCKET_STUDIO = "Access_Control_User_Id_From_Pocket_Studio";
    public static final int FLAG_ENCRYPTED = 8;
    public static final int FLAG_HIDE_ICON = 1;
    public static final int FLAG_HIDE_IN_RECENT = 2;
    public static final int FLAG_HIDE_NOTICE = 4;
    public static final String INITIALIZED_FROM_TWO_FINGER_SWIPE = "Initialized_From_Two_Finger_Swipe";
    public static final String LAUNCH_ACTIVITY_OPTIONS = "Launch_Activity_Options";
    public static final String LAUNCH_WINDOWING_MODE = "Launch_Windowing_Mode";
    public static final int MODE_EACH = 0;
    public static final int MODE_LOCK_SCREEN = 1;
    public static final String NEED_TRAVERSE_PACKAGES_WHEN_ACCESS_CHECK = "Need_Traverse_Packages_When_Access_Check";
    public static final int RUS_TYPE_FILTER = 0;
    public static final int RUS_TYPE_HIDE_KEYGUARD_LOCK = 1;
    public static final String SHOW_WHEN_LOCK = "show_when_lock";
    public static final String SOURCE_BUNDLE_FROM_POCKET_STUDIO = "Source_Bundle_from_Pocket_Studio";
    public static final String TASK_ID = "task_id";
    public static final String TYPE_ENCRYPT = "type_encrypt";
    public static final String TYPE_ENCRYPT_IGNORE_ENABLE = "type_encrypt_ignore_enable";
    public static final String TYPE_HIDE = "type_hide";
    public static final String TYPE_HIDE_IGNORE_ENABLE = "type_hide_ignore_enable";
    public static final int USER_XSPACE = 999;
    public static final String ZOOM_TO_SPLIT_SCREEN = "Zoom_To_Split_Screen";
    public static final int USER_CURRENT = android.os.UserHandle.myUserId();

    private static volatile OPlusAccessControlManager sInstance = null;

    private OPlusAccessControlManager() {
    }

    public static OPlusAccessControlManager getInstance() {
        if (sInstance == null) {
            synchronized (OPlusAccessControlManager.class) {
                if (sInstance == null) {
                    sInstance = new OPlusAccessControlManager();
                }
            }
        }
        return sInstance;
    }

    public void setAccessControlAppsInfo(String type, Map<String, Integer> accessControlInfo, int userId) {
    }

    public Map<String, Integer> getAccessControlAppsInfo(String type, int userId) {
        return null;
    }

    public void setAccessControlEnabled(String type, boolean enable, int userId) {
    }

    public boolean getAccessControlEnabled(String type, int userId) {
        return false;
    }

    public void addEncryptPass(String packageName, int windowMode, int userId) {
    }

    public boolean isEncryptPass(String packageName, int userId) {
        return false;
    }

    public boolean isEncryptedPackage(String packageName, int userId) {
        return false;
    }

    public void updateRusList(int type, List<String> addList, List<String> deleteList) {
    }

    public void setPrivacyAppsInfoForUser(Map<String, Integer> privacyInfo, boolean enabled, int userId) {
    }

    public boolean getApplicationAccessControlEnabledAsUser(String packageName, int userId) {
        return false;
    }

    public void addAccessControlPassForUser(String packageName, int windowMode, int userId) {
    }

    public Map<String, Integer> getPrivacyAppInfo(int userId) {
        return null;
    }

    public boolean isAccessControlPassForUser(String packageName, int userId) {
        return false;
    }
}
