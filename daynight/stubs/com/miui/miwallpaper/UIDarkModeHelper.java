package com.miui.miwallpaper;

/** Compile-only stub. The real class ships in the wallpaper APK; this one is never packaged. */
public class UIDarkModeHelper {
    public interface CallBack {
        void onDarkModeChanged(boolean isDark);

        void onDarkenWallpaperChanged(boolean darken);

        void onSuperWallpaperDark(boolean dark);
    }
}
