package superwallpaper.port;

import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.unity3d.player.UnityPlayer;

/**
 * Decides which display refresh-rate changes reach Unity ("Refresh_<hz>").
 *
 * <p>Stock behaviour forwards every change immediately. On Samsung the display
 * drops 120 -> 60 Hz about 5 ms after the screen-off animation starts; Unity
 * re-paces on that message and stalls a few frames, which showed up as a
 * "flash" in Earth and Saturn. So:
 * <ul>
 *   <li>Decreases are never forwarded. Unity aiming above the display rate is
 *       harmless (it simply runs at the display's rate).</li>
 *   <li>Increases above what Unity already knows are forwarded after
 *       {@link #DELAY_MS}, so they don't land mid-transition. This covers the
 *       wallpaper starting while the display is at a low rate (AOD after a
 *       reboot, or "Standard" 60 Hz motion smoothness).</li>
 * </ul>
 * Messages go straight to Unity rather than through
 * {@code SuperWallpaper.sendUnityMessage}, which would also record them as the
 * scene's state (mStateEvent) and confuse its state checks.
 *
 * <p>Patched calls (smali):
 * {@code SuperWallpaper.onCreate} calls {@link #initial} after it sends the
 * startup rate; {@code SuperWallpaper$10.onDisplayChanged} calls
 * {@link #changed} instead of sending.
 */
public final class RefreshForwarder {
    private static final String TAG = "SWRefresh";
    private static final long DELAY_MS = 2000;
    private static final String PREFIX = "Refresh_";

    private static final Handler sHandler = new Handler(Looper.getMainLooper());
    /** Highest rate Unity has been told about. */
    private static int sSent;
    /** Highest rate waiting to be forwarded, or 0. */
    private static int sPending;
    private static final Runnable sFlush = RefreshForwarder::flush;

    private RefreshForwarder() {
    }

    /** The stock code just sent this startup rate to Unity; remember it. */
    public static void initial(String message) {
        int rate = parse(message);
        if (rate > 0) {
            sSent = rate;
            Log.i(TAG, "initial " + rate + " Hz");
        }
    }

    /** The display's refresh rate changed (called on the main thread). */
    public static void changed(String message) {
        int rate = parse(message);
        if (rate <= 0) return;
        if (rate <= sSent) {
            Log.d(TAG, "not forwarding " + rate + " Hz (Unity already at " + sSent + ")");
            return;
        }
        sPending = Math.max(sPending, rate);
        sHandler.removeCallbacks(sFlush);
        sHandler.postDelayed(sFlush, DELAY_MS);
        Log.i(TAG, "will forward " + sPending + " Hz in " + DELAY_MS + " ms");
    }

    private static void flush() {
        int rate = sPending;
        sPending = 0;
        if (rate <= sSent) return;
        try {
            UnityPlayer.UnitySendMessage("Main Camera", "Message", PREFIX + rate);
            sSent = rate;
            Log.i(TAG, "forwarded " + rate + " Hz");
        } catch (Throwable t) {
            Log.w(TAG, "forward failed", t);
        }
    }

    private static int parse(String message) {
        if (message == null || !message.startsWith(PREFIX)) return -1;
        try {
            return Integer.parseInt(message.substring(PREFIX.length()));
        } catch (NumberFormatException e) {
            return -1;
        }
    }
}
