package superwallpaper.port.daynight;

import java.util.Calendar;
import java.util.TimeZone;

/**
 * Sunrise/sunset times using the US Naval Observatory "Almanac for Computers"
 * algorithm (official zenith, 90°50'). Accurate to a minute or two, which is
 * plenty for picking a wallpaper scene.
 */
final class SunCalc {
    static final int STATE_NORMAL = 0;
    static final int STATE_POLAR_DAY = 1;   // the sun doesn't set today
    static final int STATE_POLAR_NIGHT = 2; // the sun doesn't rise today

    private static final double ZENITH = 90.833;
    private static final long HOUR = 60 * 60 * 1000L;
    private static final long DAY = 24 * HOUR;

    static final class Result {
        int state;
        /** Millis; only meaningful when state == STATE_NORMAL. */
        long sunrise;
        long sunset;

        boolean isDay(long now) {
            if (state == STATE_POLAR_DAY) return true;
            if (state == STATE_POLAR_NIGHT) return false;
            return now >= sunrise && now < sunset;
        }
    }

    private SunCalc() {
    }

    /** Sunrise and sunset for the local calendar day containing {@code now}. */
    static Result forDay(long now, double lat, double lng, TimeZone zone) {
        Calendar local = Calendar.getInstance(zone);
        local.setTimeInMillis(now);
        int dayOfYear = local.get(Calendar.DAY_OF_YEAR);
        local.set(Calendar.HOUR_OF_DAY, 12);
        local.set(Calendar.MINUTE, 0);
        local.set(Calendar.SECOND, 0);
        local.set(Calendar.MILLISECOND, 0);
        long localNoon = local.getTimeInMillis();

        // The algorithm returns hours UTC; anchor them to UTC midnight of the local date.
        Calendar utc = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
        utc.clear();
        utc.set(local.get(Calendar.YEAR), local.get(Calendar.MONTH), local.get(Calendar.DAY_OF_MONTH));
        long utcMidnight = utc.getTimeInMillis();

        Result r = new Result();
        double rise = utcHours(dayOfYear, lat, lng, true);
        double set = utcHours(dayOfYear, lat, lng, false);
        if (Double.isInfinite(rise) || Double.isInfinite(set)) {
            boolean polarDay = rise == Double.POSITIVE_INFINITY || set == Double.POSITIVE_INFINITY;
            r.state = polarDay ? STATE_POLAR_DAY : STATE_POLAR_NIGHT;
            return r;
        }
        r.state = STATE_NORMAL;
        // UTC hours can land on the neighbouring UTC day; pull each time to within 12h of local noon.
        r.sunrise = nearNoon(utcMidnight + (long) (rise * HOUR), localNoon);
        r.sunset = nearNoon(utcMidnight + (long) (set * HOUR), localNoon);
        if (r.sunset <= r.sunrise) r.sunset += DAY;
        return r;
    }

    private static long nearNoon(long t, long noon) {
        while (t - noon > DAY / 2) t -= DAY;
        while (noon - t > DAY / 2) t += DAY;
        return t;
    }

    /**
     * @return the event time in hours UTC (0..24), +Infinity if the sun never
     *         sets that day, or -Infinity if it never rises.
     */
    private static double utcHours(int dayOfYear, double lat, double lng, boolean sunrise) {
        double lngHour = lng / 15;
        double t = dayOfYear + ((sunrise ? 6 : 18) - lngHour) / 24;

        double meanAnomaly = 0.9856 * t - 3.289;
        double trueLng = norm360(meanAnomaly + 1.916 * sin(meanAnomaly)
                + 0.020 * sin(2 * meanAnomaly) + 282.634);

        double ra = norm360(Math.toDegrees(Math.atan(0.91764 * tan(trueLng))));
        // Put right ascension in the same quadrant as the true longitude, then convert to hours.
        ra = (ra + (Math.floor(trueLng / 90) * 90 - Math.floor(ra / 90) * 90)) / 15;

        double sinDec = 0.39782 * sin(trueLng);
        double cosDec = Math.cos(Math.asin(sinDec));
        double cosH = (cos(ZENITH) - sinDec * sin(lat)) / (cosDec * cos(lat));
        if (cosH > 1) return Double.NEGATIVE_INFINITY; // never rises
        if (cosH < -1) return Double.POSITIVE_INFINITY; // never sets

        double h = Math.toDegrees(Math.acos(cosH));
        if (sunrise) h = 360 - h;
        h /= 15;

        double localMeanTime = h + ra - 0.06571 * t - 6.622;
        double ut = (localMeanTime - lngHour) % 24;
        return ut < 0 ? ut + 24 : ut;
    }

    private static double norm360(double deg) {
        double d = deg % 360;
        return d < 0 ? d + 360 : d;
    }

    private static double sin(double deg) {
        return Math.sin(Math.toRadians(deg));
    }

    private static double cos(double deg) {
        return Math.cos(Math.toRadians(deg));
    }

    private static double tan(double deg) {
        return Math.tan(Math.toRadians(deg));
    }
}
