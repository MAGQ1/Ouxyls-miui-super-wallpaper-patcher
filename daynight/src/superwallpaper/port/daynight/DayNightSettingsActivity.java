package superwallpaper.port.daynight;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.TimePickerDialog;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.res.TypedArray;
import android.graphics.Typeface;
import android.location.Location;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.text.DateFormat;
import java.util.Calendar;
import java.util.Locale;
import java.util.TimeZone;

/**
 * Launcher screen ("Mars wallpaper") for choosing when the day and night scenes
 * show. Built in code so the patch doesn't need to add any resources to the APK.
 */
public class DayNightSettingsActivity extends Activity {
    private static final int REQUEST_LOCATION = 1;
    /** Use a cached fix if it's newer than this; otherwise ask for a fresh one. */
    private static final long MAX_LOCATION_AGE = 24 * 60 * 60 * 1000L;

    private static final int[] MODES = {
            DayNightSettings.MODE_SYSTEM,
            DayNightSettings.MODE_SUN,
            DayNightSettings.MODE_SCHEDULE,
            DayNightSettings.MODE_DAY,
            DayNightSettings.MODE_NIGHT,
    };
    private static final String[] MODE_TITLES = {
            "Follow dark mode",
            "Follow sunrise and sunset",
            "Custom times",
            "Always day",
            "Always night",
    };
    private static final String[] MODE_SUMMARIES = {
            "Night when the phone is in dark mode, day otherwise.",
            "Day between local sunrise and sunset. Needs your approximate location.",
            "Day and night start at times you pick.",
            "Always show the day scene.",
            "Always show the night scene.",
    };

    private DayNightSettings mSettings;
    private LinearLayout mSunSection;
    private TextView mLocationText;
    private TextView mSunTimesText;
    private LinearLayout mScheduleSection;
    private Button mDayStartButton;
    private Button mNightStartButton;
    private TextView mStatusText;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        setTheme(Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q
                ? android.R.style.Theme_DeviceDefault_DayNight
                : android.R.style.Theme_DeviceDefault);
        super.onCreate(savedInstanceState);
        setTitle("Day & night");
        mSettings = DayNightSettings.load(this);
        setContentView(buildContent());
        refresh();
    }

    private View buildContent() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int side = dp(20);
        root.setPadding(side, dp(16), side, dp(32));
        root.addView(text("Choose when the wallpaper shows its day and night scenes.", 15, false));

        RadioGroup modes = new RadioGroup(this);
        modes.setPadding(0, dp(12), 0, dp(4));
        for (int i = 0; i < MODES.length; i++) {
            RadioButton rb = new RadioButton(this);
            rb.setId(View.generateViewId());
            rb.setText(MODE_TITLES[i] + "\n" + MODE_SUMMARIES[i]);
            rb.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
            rb.setPadding(dp(8), dp(10), 0, dp(10));
            rb.setTag(MODES[i]);
            modes.addView(rb);
            if (mSettings.mode == MODES[i]) rb.setChecked(true);
        }
        modes.setOnCheckedChangeListener((group, checkedId) -> {
            View v = group.findViewById(checkedId);
            if (v == null) return;
            mSettings.mode = (Integer) v.getTag();
            if (mSettings.mode == DayNightSettings.MODE_SUN && !mSettings.hasLocation) {
                requestLocation();
            }
            saveAndApply();
        });
        root.addView(modes);

        // Shown for "Follow sunrise and sunset".
        mSunSection = section(root, "Location");
        mLocationText = text("", 15, false);
        mSunSection.addView(mLocationText);
        mSunTimesText = text("", 15, false);
        mSunTimesText.setPadding(0, dp(4), 0, dp(8));
        mSunSection.addView(mSunTimesText);
        LinearLayout locationButtons = row();
        locationButtons.addView(button("Use my location", v -> requestLocation()));
        locationButtons.addView(button("Enter coordinates", v -> showCoordinateDialog()));
        mSunSection.addView(locationButtons);
        TextView privacy = text("Your location is rounded to about 1 km and only stored on this phone. "
                + "Open this screen again after travelling to update it.", 13, false);
        privacy.setAlpha(0.7f);
        privacy.setPadding(0, dp(8), 0, 0);
        mSunSection.addView(privacy);

        // Shown for "Custom times", and for sunrise/sunset until a location is set.
        mScheduleSection = section(root, "Times");
        LinearLayout timeButtons = row();
        mDayStartButton = button("", v -> pickTime(true));
        mNightStartButton = button("", v -> pickTime(false));
        timeButtons.addView(mDayStartButton);
        timeButtons.addView(mNightStartButton);
        mScheduleSection.addView(timeButtons);

        mStatusText = text("", 15, true);
        mStatusText.setPadding(0, dp(24), 0, 0);
        root.addView(mStatusText);

        ScrollView scroll = new ScrollView(this);
        scroll.setFitsSystemWindows(true);
        scroll.addView(root);
        return scroll;
    }

    private void refresh() {
        int mode = mSettings.mode;
        boolean sun = mode == DayNightSettings.MODE_SUN;
        boolean schedule = mode == DayNightSettings.MODE_SCHEDULE || (sun && !mSettings.hasLocation);
        mSunSection.setVisibility(sun ? View.VISIBLE : View.GONE);
        mScheduleSection.setVisibility(schedule ? View.VISIBLE : View.GONE);

        if (mSettings.hasLocation) {
            mLocationText.setText(String.format(Locale.US, "Using %.2f, %.2f", mSettings.lat, mSettings.lng));
            SunCalc.Result today = SunCalc.forDay(System.currentTimeMillis(),
                    mSettings.lat, mSettings.lng, TimeZone.getDefault());
            if (today.state == SunCalc.STATE_POLAR_DAY) {
                mSunTimesText.setText("Today: the sun doesn't set");
            } else if (today.state == SunCalc.STATE_POLAR_NIGHT) {
                mSunTimesText.setText("Today: the sun doesn't rise");
            } else {
                DateFormat fmt = android.text.format.DateFormat.getTimeFormat(this);
                mSunTimesText.setText("Today: sunrise " + fmt.format(today.sunrise)
                        + ", sunset " + fmt.format(today.sunset));
            }
        } else {
            mLocationText.setText("No location set yet. Until then the custom times below are used.");
            mSunTimesText.setText("");
        }

        mDayStartButton.setText("Day starts\n" + formatMinutes(mSettings.dayStartMin));
        mNightStartButton.setText("Night starts\n" + formatMinutes(mSettings.nightStartMin));
        mStatusText.setText("Right now: " + (DayNightController.isDayNow(this) ? "day" : "night") + " scene");
    }

    private void saveAndApply() {
        mSettings.save(this);
        DayNightController.settingsChanged(this);
        refresh();
    }

    // ---- Location ---------------------------------------------------------

    private void requestLocation() {
        if (checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.ACCESS_COARSE_LOCATION}, REQUEST_LOCATION);
        } else {
            fetchLocation();
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        if (requestCode != REQUEST_LOCATION) return;
        if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            fetchLocation();
        } else {
            toast("Location permission denied. You can enter coordinates instead.");
        }
    }

    private void fetchLocation() {
        LocationManager lm = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        if (lm == null) {
            toast("Location isn't available on this device.");
            return;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P && !lm.isLocationEnabled()) {
            toast("Turn on Location, then try again.");
            startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS));
            return;
        }

        // Newest cached fix from any provider.
        Location cached = null;
        for (String provider : lm.getProviders(true)) {
            try {
                Location l = lm.getLastKnownLocation(provider);
                if (l != null && (cached == null || l.getTime() > cached.getTime())) cached = l;
            } catch (SecurityException ignored) {
            }
        }

        if (cached != null && System.currentTimeMillis() - cached.getTime() < MAX_LOCATION_AGE) {
            setLocation(cached.getLatitude(), cached.getLongitude());
            return;
        }

        String provider = Build.VERSION.SDK_INT >= Build.VERSION_CODES.R ? pickProvider(lm) : null;
        if (provider != null) {
            toast("Finding your location…");
            final Location stale = cached;
            lm.getCurrentLocation(provider, null, getMainExecutor(), fresh -> {
                // If a fresh fix fails, an old cached one is still better than nothing.
                Location l = fresh != null ? fresh : stale;
                if (l != null) {
                    setLocation(l.getLatitude(), l.getLongitude());
                } else {
                    toast("Couldn't get your location. You can enter coordinates instead.");
                }
            });
        } else if (cached != null) {
            setLocation(cached.getLatitude(), cached.getLongitude());
        } else {
            toast("Couldn't get your location. You can enter coordinates instead.");
        }
    }

    private static String pickProvider(LocationManager lm) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
                && lm.hasProvider(LocationManager.FUSED_PROVIDER)
                && lm.isProviderEnabled(LocationManager.FUSED_PROVIDER)) {
            return LocationManager.FUSED_PROVIDER;
        }
        if (lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) return LocationManager.NETWORK_PROVIDER;
        if (lm.isProviderEnabled(LocationManager.GPS_PROVIDER)) return LocationManager.GPS_PROVIDER;
        return null;
    }

    private void setLocation(double lat, double lng) {
        if (isFinishing() || isDestroyed()) return;
        // Two decimal places is roughly 1 km: enough for sunrise/sunset, and less identifying.
        mSettings.lat = Math.round(lat * 100) / 100.0;
        mSettings.lng = Math.round(lng * 100) / 100.0;
        mSettings.hasLocation = true;
        saveAndApply();
        toast("Location updated");
    }

    private void showCoordinateDialog() {
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(24), dp(8), dp(24), 0);
        EditText latField = coordinateField("Latitude (e.g. 40.71)");
        EditText lngField = coordinateField("Longitude (e.g. -74.01)");
        if (mSettings.hasLocation) {
            latField.setText(String.format(Locale.US, "%.2f", mSettings.lat));
            lngField.setText(String.format(Locale.US, "%.2f", mSettings.lng));
        }
        form.addView(latField);
        form.addView(lngField);

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("Enter coordinates")
                .setView(form)
                .setNegativeButton(android.R.string.cancel, null)
                .setPositiveButton(android.R.string.ok, null)
                .create();
        // Override the OK button so invalid input keeps the dialog open.
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            try {
                double lat = Double.parseDouble(latField.getText().toString().trim());
                double lng = Double.parseDouble(lngField.getText().toString().trim());
                if (lat < -90 || lat > 90 || lng < -180 || lng > 180) throw new NumberFormatException();
                setLocation(lat, lng);
                dialog.dismiss();
            } catch (NumberFormatException e) {
                toast("Latitude must be -90 to 90 and longitude -180 to 180.");
            }
        }));
        dialog.show();
    }

    private EditText coordinateField(String hint) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setSingleLine(true);
        e.setInputType(InputType.TYPE_CLASS_NUMBER
                | InputType.TYPE_NUMBER_FLAG_SIGNED
                | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        return e;
    }

    // ---- Times ------------------------------------------------------------

    private void pickTime(boolean dayStart) {
        int current = dayStart ? mSettings.dayStartMin : mSettings.nightStartMin;
        new TimePickerDialog(this, (picker, hour, minute) -> {
            if (dayStart) {
                mSettings.dayStartMin = hour * 60 + minute;
            } else {
                mSettings.nightStartMin = hour * 60 + minute;
            }
            saveAndApply();
        }, current / 60, current % 60, android.text.format.DateFormat.is24HourFormat(this)).show();
    }

    private String formatMinutes(int minutes) {
        Calendar c = Calendar.getInstance();
        c.set(Calendar.HOUR_OF_DAY, minutes / 60);
        c.set(Calendar.MINUTE, minutes % 60);
        return android.text.format.DateFormat.getTimeFormat(this).format(c.getTime());
    }

    // ---- Small view helpers -----------------------------------------------

    private LinearLayout section(LinearLayout parent, String title) {
        LinearLayout s = new LinearLayout(this);
        s.setOrientation(LinearLayout.VERTICAL);
        s.setPadding(0, dp(20), 0, 0);
        TextView header = text(title, 14, true);
        header.setTextColor(accentColor());
        header.setPadding(0, 0, 0, dp(8));
        s.addView(header);
        parent.addView(s);
        return s;
    }

    private LinearLayout row() {
        LinearLayout r = new LinearLayout(this);
        r.setOrientation(LinearLayout.HORIZONTAL);
        return r;
    }

    private Button button(String label, View.OnClickListener onClick) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setGravity(Gravity.CENTER);
        b.setOnClickListener(onClick);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        lp.setMarginEnd(dp(8));
        b.setLayoutParams(lp);
        return b;
    }

    private TextView text(String s, int sp, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        if (bold) t.setTypeface(t.getTypeface(), Typeface.BOLD);
        return t;
    }

    private int accentColor() {
        TypedArray a = obtainStyledAttributes(new int[]{android.R.attr.colorAccent});
        int color = a.getColor(0, 0xFF3D7BF7); // fallback blue if the theme has no accent
        a.recycle();
        return color;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }
}
