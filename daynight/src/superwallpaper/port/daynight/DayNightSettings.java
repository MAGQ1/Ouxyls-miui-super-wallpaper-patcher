package superwallpaper.port.daynight;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.Calendar;
import java.util.TimeZone;

/**
 * The user's day/night choice, persisted in device-protected storage so the
 * wallpaper can read it before the phone is unlocked after a reboot.
 */
final class DayNightSettings {
    static final int MODE_SYSTEM = 0;   // follow the system dark mode (stock behaviour)
    static final int MODE_SUN = 1;      // day between local sunrise and sunset
    static final int MODE_SCHEDULE = 2; // day and night start at fixed times
    static final int MODE_DAY = 3;      // always day
    static final int MODE_NIGHT = 4;    // always night

    // Historical name (the module started in Mars). Kept so existing settings survive updates;
    // each wallpaper app has its own copy anyway.
    private static final String FILE = "mars_daynight";
    private static final String KEY_MODE = "mode";
    private static final String KEY_HAS_LOCATION = "has_location";
    private static final String KEY_LAT = "lat";
    private static final String KEY_LNG = "lng";
    private static final String KEY_DAY_START = "day_start_min";
    private static final String KEY_NIGHT_START = "night_start_min";

    private static final int DEFAULT_DAY_START = 7 * 60;    // 07:00
    private static final int DEFAULT_NIGHT_START = 19 * 60; // 19:00

    int mode = MODE_SYSTEM;
    boolean hasLocation;
    double lat;
    double lng;
    /** Minutes after local midnight. */
    int dayStartMin = DEFAULT_DAY_START;
    int nightStartMin = DEFAULT_NIGHT_START;

    static DayNightSettings load(Context context) {
        SharedPreferences p = prefs(context);
        DayNightSettings s = new DayNightSettings();
        s.mode = p.getInt(KEY_MODE, MODE_SYSTEM);
        s.hasLocation = p.getBoolean(KEY_HAS_LOCATION, false);
        // Doubles are stored as their raw bits; SharedPreferences has no putDouble.
        s.lat = Double.longBitsToDouble(p.getLong(KEY_LAT, 0));
        s.lng = Double.longBitsToDouble(p.getLong(KEY_LNG, 0));
        s.dayStartMin = p.getInt(KEY_DAY_START, DEFAULT_DAY_START);
        s.nightStartMin = p.getInt(KEY_NIGHT_START, DEFAULT_NIGHT_START);
        return s;
    }

    void save(Context context) {
        prefs(context).edit()
                .putInt(KEY_MODE, mode)
                .putBoolean(KEY_HAS_LOCATION, hasLocation)
                .putLong(KEY_LAT, Double.doubleToRawLongBits(lat))
                .putLong(KEY_LNG, Double.doubleToRawLongBits(lng))
                .putInt(KEY_DAY_START, dayStartMin)
                .putInt(KEY_NIGHT_START, nightStartMin)
                .apply();
    }

    /**
     * @param now        wall-clock time in millis
     * @param systemDark whether the system is currently in dark mode
     */
    boolean isDay(long now, boolean systemDark) {
        switch (mode) {
            case MODE_SUN:
                // Without a location we can't compute the sun, so fall back to the custom times.
                if (!hasLocation) return isScheduledDay(now);
                return SunCalc.forDay(now, lat, lng, TimeZone.getDefault()).isDay(now);
            case MODE_SCHEDULE:
                return isScheduledDay(now);
            case MODE_DAY:
                return true;
            case MODE_NIGHT:
                return false;
            case MODE_SYSTEM:
            default:
                return !systemDark;
        }
    }

    private boolean isScheduledDay(long now) {
        Calendar c = Calendar.getInstance();
        c.setTimeInMillis(now);
        int minute = c.get(Calendar.HOUR_OF_DAY) * 60 + c.get(Calendar.MINUTE);
        if (dayStartMin == nightStartMin) return true;
        if (dayStartMin < nightStartMin) {
            return minute >= dayStartMin && minute < nightStartMin;
        }
        // Day wraps past midnight (e.g. day starts 22:00, night starts 06:00).
        return minute >= dayStartMin || minute < nightStartMin;
    }

    private static SharedPreferences prefs(Context context) {
        return context.createDeviceProtectedStorageContext()
                .getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }
}
