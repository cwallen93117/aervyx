package com.aervyx.aervyx_mobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.os.BatteryManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper

class PersistentRuntimeService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private val batteryCheckRunnable =
        object : Runnable {
            override fun run() {
                if (stopIfBatteryTooLow()) return
                handler.postDelayed(this, BATTERY_CHECK_INTERVAL_MS)
            }
        }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel(this)
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            setRuntimeEnabled(this, false)
            stopForegroundCompat()
            stopSelf()
            return START_NOT_STICKY
        }

        if (!isRuntimeEnabled(this)) {
            stopForegroundCompat()
            stopSelf()
            return START_NOT_STICKY
        }

        if (stopIfBatteryTooLow()) {
            return START_NOT_STICKY
        }

        if (!promoteToForeground()) {
            return START_NOT_STICKY
        }

        startBatteryMonitor()
        return START_STICKY
    }

    override fun onDestroy() {
        handler.removeCallbacks(batteryCheckRunnable)
        stopForegroundCompat()
        super.onDestroy()
    }

    private fun promoteToForeground(): Boolean {
        return try {
            val notification = buildNotification()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID, notification, foregroundTypeMask())
            } else {
                @Suppress("DEPRECATION")
                startForeground(NOTIFICATION_ID, notification)
            }
            true
        } catch (e: SecurityException) {
            showRestoreNotification(this)
            stopSelf()
            false
        } catch (e: RuntimeException) {
            if (
                Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
                e.javaClass.name == "android.app.ForegroundServiceStartNotAllowedException"
            ) {
                showRestoreNotification(this)
                stopSelf()
                false
            } else {
                throw e
            }
        }
    }

    private fun foregroundTypeMask(): Int {
        var mask = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
        if (isBleActive(this)) {
            mask = mask or ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE
        }
        return mask
    }

    private fun buildNotification(): Notification {
        val launchIntent =
            packageManager.getLaunchIntentForPackage(packageName)
                ?: Intent(this, MainActivity::class.java)
        val contentIntent = PendingIntent.getActivity(
            this,
            0,
            launchIntent,
            pendingIntentFlags(PendingIntent.FLAG_UPDATE_CURRENT),
        )
        val builder =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                Notification.Builder(this, CHANNEL_ID)
            } else {
                @Suppress("DEPRECATION")
                Notification.Builder(this)
            }

        builder
            .setSmallIcon(R.drawable.ic_stat_aervyx)
            .setContentTitle("Aervyx is running")
            .setContentText(notificationText(this))
            .setOngoing(true)
            .setShowWhen(false)
            .setContentIntent(contentIntent)

        return builder.build()
    }

    private fun stopForegroundCompat() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
    }

    private fun startBatteryMonitor() {
        handler.removeCallbacks(batteryCheckRunnable)
        handler.postDelayed(batteryCheckRunnable, BATTERY_CHECK_INTERVAL_MS)
    }

    private fun stopIfBatteryTooLow(): Boolean {
        val threshold = getAutoExitBatteryThreshold(this) ?: return false
        val snapshot = getBatterySnapshot(this) ?: return false
        if (snapshot.isCharging || snapshot.level > threshold) return false

        setRuntimeEnabled(this, false)
        showBatteryShutdownNotification(this, snapshot.level, threshold)
        stopForegroundCompat()
        stopSelf()
        return true
    }

    companion object {
        private const val ACTION_START = "com.aervyx.aervyx_mobile.runtime.START"
        private const val ACTION_UPDATE = "com.aervyx.aervyx_mobile.runtime.UPDATE"
        private const val ACTION_STOP = "com.aervyx.aervyx_mobile.runtime.STOP"
        private const val CHANNEL_ID = "aervyx_persistent_runtime"
        private const val CHANNEL_NAME = "Aervyx Runtime"
        private const val NOTIFICATION_ID = 889
        private const val RESTORE_NOTIFICATION_ID = 890
        private const val PREFS = "aervyx_persistent_runtime"
        private const val KEY_ENABLED = "enabled"
        private const val KEY_BLE_ACTIVE = "ble_active"
        private const val KEY_LOCATION_ACTIVE = "location_active"
        private const val KEY_AUTO_EXIT_BATTERY_THRESHOLD = "auto_exit_battery_threshold"
        private const val DEFAULT_AUTO_EXIT_BATTERY_THRESHOLD = 5
        private const val BATTERY_CHECK_INTERVAL_MS = 60_000L

        fun start(context: Context) {
            setRuntimeEnabled(context, true)
            requestStart(context, ACTION_START)
        }

        fun ensureRunning(context: Context) {
            if (isRuntimeEnabled(context)) {
                requestStart(context, ACTION_START)
            }
        }

        fun stop(context: Context) {
            setRuntimeEnabled(context, false)
            context.stopService(Intent(context, PersistentRuntimeService::class.java))
        }

        fun setBleActive(context: Context, active: Boolean) {
            prefs(context).edit().putBoolean(KEY_BLE_ACTIVE, active).apply()
            if (isRuntimeEnabled(context)) {
                requestStart(context, ACTION_UPDATE)
            }
        }

        fun setLocationActive(context: Context, active: Boolean) {
            prefs(context).edit().putBoolean(KEY_LOCATION_ACTIVE, active).apply()
            if (isRuntimeEnabled(context)) {
                requestStart(context, ACTION_UPDATE)
            }
        }

        fun setAutoExitBatteryThreshold(context: Context, threshold: Int?) {
            val sanitized = threshold?.coerceIn(1, 50) ?: 0
            prefs(context).edit().putInt(KEY_AUTO_EXIT_BATTERY_THRESHOLD, sanitized).apply()
            if (isRuntimeEnabled(context)) {
                requestStart(context, ACTION_UPDATE)
            }
        }

        fun getAutoExitBatteryThreshold(context: Context): Int? {
            val threshold = prefs(context).getInt(
                KEY_AUTO_EXIT_BATTERY_THRESHOLD,
                DEFAULT_AUTO_EXIT_BATTERY_THRESHOLD,
            )
            return if (threshold > 0) threshold else null
        }

        fun getBatteryLevel(context: Context): Int? = getBatterySnapshot(context)?.level

        fun isBatteryCharging(context: Context): Boolean? =
            getBatterySnapshot(context)?.isCharging

        fun isRuntimeEnabled(context: Context): Boolean =
            prefs(context).getBoolean(KEY_ENABLED, false)

        private fun requestStart(context: Context, action: String) {
            val intent = Intent(context, PersistentRuntimeService::class.java)
                .setAction(action)
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            } catch (_: Exception) {
                showRestoreNotification(context)
            }
        }

        private fun setRuntimeEnabled(context: Context, enabled: Boolean) {
            prefs(context).edit().putBoolean(KEY_ENABLED, enabled).apply()
        }

        private fun isBleActive(context: Context): Boolean =
            prefs(context).getBoolean(KEY_BLE_ACTIVE, false)

        private fun isLocationActive(context: Context): Boolean =
            prefs(context).getBoolean(KEY_LOCATION_ACTIVE, false)

        private fun notificationText(context: Context): String {
            val pieces = mutableListOf("persistent runtime")
            if (isLocationActive(context)) {
                pieces.add("GPS active")
            }
            if (isBleActive(context)) {
                pieces.add("mesh active")
            }
            return pieces.joinToString(" - ").replaceFirstChar { it.uppercase() }
        }

        fun showRestoreNotification(context: Context) {
            createNotificationChannel(context)
            val launchIntent =
                context.packageManager.getLaunchIntentForPackage(context.packageName)
                    ?: Intent(context, MainActivity::class.java)
            val contentIntent = PendingIntent.getActivity(
                context,
                2,
                launchIntent,
                pendingIntentFlags(PendingIntent.FLAG_UPDATE_CURRENT),
            )
            val builder =
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    Notification.Builder(context, CHANNEL_ID)
                } else {
                    @Suppress("DEPRECATION")
                    Notification.Builder(context)
                }

            val notification = builder
                .setSmallIcon(R.drawable.ic_stat_aervyx)
                .setContentTitle("Open Aervyx to resume")
                .setContentText("Android paused the persistent runtime.")
                .setContentIntent(contentIntent)
                .setAutoCancel(true)
                .build()

            val manager =
                context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.notify(RESTORE_NOTIFICATION_ID, notification)
        }

        private fun showBatteryShutdownNotification(
            context: Context,
            level: Int,
            threshold: Int,
        ) {
            createNotificationChannel(context)
            val launchIntent =
                context.packageManager.getLaunchIntentForPackage(context.packageName)
                    ?: Intent(context, MainActivity::class.java)
            val contentIntent = PendingIntent.getActivity(
                context,
                3,
                launchIntent,
                pendingIntentFlags(PendingIntent.FLAG_UPDATE_CURRENT),
            )
            val builder =
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    Notification.Builder(context, CHANNEL_ID)
                } else {
                    @Suppress("DEPRECATION")
                    Notification.Builder(context)
                }

            val notification = builder
                .setSmallIcon(R.drawable.ic_stat_aervyx)
                .setContentTitle("Aervyx stopped to save battery")
                .setContentText("Battery is $level%, at or below the $threshold% limit.")
                .setContentIntent(contentIntent)
                .setAutoCancel(true)
                .build()

            try {
                val manager =
                    context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                manager.notify(RESTORE_NOTIFICATION_ID, notification)
            } catch (_: SecurityException) {
                // Notification permission can be denied on Android 13+.
            }
        }

        private fun createNotificationChannel(context: Context) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
            val manager =
                context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_LOW,
            )
            channel.description = "Keeps Aervyx running until you shut it down."
            manager.createNotificationChannel(channel)
        }

        private fun prefs(context: Context) =
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

        private fun getBatterySnapshot(context: Context): BatterySnapshot? {
            val battery = context.registerReceiver(
                null,
                IntentFilter(Intent.ACTION_BATTERY_CHANGED),
            ) ?: return null
            val level = battery.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
            val scale = battery.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
            if (level < 0 || scale <= 0) return null

            val status = battery.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
            val isCharging =
                status == BatteryManager.BATTERY_STATUS_CHARGING ||
                    status == BatteryManager.BATTERY_STATUS_FULL

            return BatterySnapshot(
                level = ((level * 100f) / scale).toInt(),
                isCharging = isCharging,
            )
        }

        private fun pendingIntentFlags(baseFlags: Int): Int {
            var flags = baseFlags
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                flags = flags or PendingIntent.FLAG_IMMUTABLE
            }
            return flags
        }

        private data class BatterySnapshot(
            val level: Int,
            val isCharging: Boolean,
        )
    }
}
