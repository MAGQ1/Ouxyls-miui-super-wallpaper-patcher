package superwallpaper.port.daynight;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.PowerManager;
import android.util.Log;

import com.miui.miwallpaper.MiWallpaperBaseApplication;
import com.miui.miwallpaper.UIDarkModeHelper;

import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.Iterator;

/**
 * Decides whether the wallpaper shows its day or night scene.
 *
 * <p>The patched APK calls {@link #resolve} at the top of
 * {@code SuperWallpaper$1.onDarkModeChanged(boolean isDark)} and replaces
 * {@code isDark} with the result, so the stock wallpaper code does the actual
 * scene switch. To switch when the time of day changes (rather than when dark
 * mode changes), we remember those callbacks and call them again ourselves.
 */
public final class DayNightController {
    private static final String TAG = "MarsDayNight";

    private static final ArrayList<WeakReference<UIDarkModeHelper.CallBack>> sCallbacks = new ArrayList<>();
    private static DayNightSettings sSettings;
    private static boolean sStarted;
    /** Last dark-mode value the system reported. */
    private static boolean sSystemDark;
    /** Last value we handed back to the wallpaper. */
    private static boolean sAppliedDark;
    private static boolean sHaveApplied;

    private DayNightController() {
    }

    /**
     * Hook entry point. Must keep this exact signature: the patched smali calls
     * {@code resolve(Lcom/miui/miwallpaper/UIDarkModeHelper$CallBack;Z)Z}.
     *
     * @param callback   the wallpaper's dark-mode callback (re-invoked later on time changes)
     * @param systemDark the dark-mode value the system reported
     * @return whether the wallpaper should show its night scene
     */
    public static boolean resolve(UIDarkModeHelper.CallBack callback, boolean systemDark) {
        try {
            Context context = MiWallpaperBaseApplication.getInstance();
            addCallback(callback);
            sSystemDark = systemDark;
            start(context);
            boolean dark = !settings(context).isDay(System.currentTimeMillis(), systemDark);
            sAppliedDark = dark;
            sHaveApplied = true;
            Log.i(TAG, "resolve systemDark=" + systemDark + " mode=" + settings(context).mode
                    + " -> " + (dark ? "Night" : "Day"));
            return dark;
        } catch (Throwable t) {
            // Never break the wallpaper: fall back to stock behaviour.
            Log.w(TAG, "resolve failed, using system dark mode", t);
            return systemDark;
        }
    }

    /** Called by the settings screen after the user changes something. */
    static void settingsChanged(Context context) {
        sSettings = DayNightSettings.load(context);
        reevaluate(context, true);
    }

    static boolean isDayNow(Context context) {
        return settings(context).isDay(System.currentTimeMillis(), sSystemDark);
    }

    private static DayNightSettings settings(Context context) {
        if (sSettings == null) sSettings = DayNightSettings.load(context);
        return sSettings;
    }

    private static void addCallback(UIDarkModeHelper.CallBack callback) {
        if (callback == null) return;
        for (Iterator<WeakReference<UIDarkModeHelper.CallBack>> it = sCallbacks.iterator(); it.hasNext(); ) {
            UIDarkModeHelper.CallBack existing = it.next().get();
            if (existing == null) {
                it.remove();
            } else if (existing == callback) {
                return;
            }
        }
        sCallbacks.add(new WeakReference<>(callback));
    }

    /** Registers (once) for the broadcasts that can change day vs night. */
    private static void start(Context context) {
        if (sStarted) return;
        sStarted = true;
        IntentFilter filter = new IntentFilter();
        filter.addAction(Intent.ACTION_TIME_TICK); // every minute while the process is alive
        filter.addAction(Intent.ACTION_TIME_CHANGED);
        filter.addAction(Intent.ACTION_TIMEZONE_CHANGED);
        filter.addAction(Intent.ACTION_DATE_CHANGED);
        filter.addAction(Intent.ACTION_SCREEN_ON);
        filter.addAction(Intent.ACTION_USER_PRESENT);
        // Only protected system broadcasts, so no RECEIVER_EXPORTED flag is needed.
        context.registerReceiver(new BroadcastReceiver() {
            @Override
            public void onReceive(Context c, Intent intent) {
                reevaluate(c, false);
            }
        }, filter);
    }

    /**
     * Re-checks day vs night and, if it changed, re-runs the wallpaper's callbacks.
     *
     * @param force switch even if the screen is off. Otherwise we wait for
     *              SCREEN_ON so the user never sees the scene change mid-view.
     */
    private static void reevaluate(Context context, boolean force) {
        try {
            boolean dark = !settings(context).isDay(System.currentTimeMillis(), sSystemDark);
            if (sHaveApplied && dark == sAppliedDark) return;
            if (!force) {
                PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
                if (pm != null && !pm.isInteractive()) return;
            }
            Log.i(TAG, "switching to " + (dark ? "Night" : "Day"));
            // Each callback goes back through the hook, which calls resolve() and applies our answer.
            for (WeakReference<UIDarkModeHelper.CallBack> ref : new ArrayList<>(sCallbacks)) {
                UIDarkModeHelper.CallBack cb = ref.get();
                if (cb != null) cb.onDarkModeChanged(sSystemDark);
            }
        } catch (Throwable t) {
            Log.w(TAG, "reevaluate failed", t);
        }
    }
}
