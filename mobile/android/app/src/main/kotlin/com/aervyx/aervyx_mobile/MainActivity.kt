package com.aervyx.aervyx_mobile

import android.content.Intent
import android.net.Uri
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.aervyx.aervyx_mobile/persistent_runtime",
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "start" -> {
                    PersistentRuntimeService.start(this)
                    result.success(true)
                }

                "stop" -> {
                    PersistentRuntimeService.stop(this)
                    result.success(true)
                }

                "setBleActive" -> {
                    val active = call.argument<Boolean>("active") == true
                    PersistentRuntimeService.setBleActive(this, active)
                    result.success(true)
                }

                "setLocationActive" -> {
                    val active = call.argument<Boolean>("active") == true
                    PersistentRuntimeService.setLocationActive(this, active)
                    result.success(true)
                }

                "isEnabled" -> {
                    result.success(PersistentRuntimeService.isRuntimeEnabled(this))
                }

                "setAutoExitBatteryThreshold" -> {
                    val threshold = call.argument<Int>("threshold")
                    PersistentRuntimeService.setAutoExitBatteryThreshold(this, threshold)
                    result.success(true)
                }

                "getAutoExitBatteryThreshold" -> {
                    result.success(PersistentRuntimeService.getAutoExitBatteryThreshold(this))
                }

                "getBatteryLevel" -> {
                    result.success(PersistentRuntimeService.getBatteryLevel(this))
                }

                "isBatteryCharging" -> {
                    result.success(PersistentRuntimeService.isBatteryCharging(this))
                }

                "openBatteryOptimizationSettings" -> {
                    try {
                        startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                        result.success(true)
                    } catch (_: Exception) {
                        val uri = Uri.parse("package:$packageName")
                        startActivity(
                            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, uri),
                        )
                        result.success(true)
                    }
                }

                else -> result.notImplemented()
            }
        }
    }
}
