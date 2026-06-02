package com.aervyx.aervyx_mobile

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import java.io.File
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
    }

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

        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.aervyx.aervyx_mobile/app_update",
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "installApk" -> {
                    val path = call.argument<String>("path")
                    if (path.isNullOrBlank()) {
                        result.error("INVALID_PATH", "APK path is required", null)
                        return@setMethodCallHandler
                    }
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
                        !packageManager.canRequestPackageInstalls()
                    ) {
                        result.error(
                            "INSTALL_PERMISSION_REQUIRED",
                            "Aervyx needs permission to install app updates",
                            null,
                        )
                        return@setMethodCallHandler
                    }

                    val apkFile = File(path)
                    if (!apkFile.exists()) {
                        result.error("FILE_NOT_FOUND", "Downloaded APK was not found", null)
                        return@setMethodCallHandler
                    }

                    val apkUri = FileProvider.getUriForFile(
                        this,
                        "$packageName.fileprovider",
                        apkFile,
                    )
                    val intent = Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(apkUri, "application/vnd.android.package-archive")
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                    startActivity(intent)
                    result.success(true)
                }

                "openInstallPermissionSettings" -> {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        val uri = Uri.parse("package:$packageName")
                        startActivity(
                            Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, uri),
                        )
                    } else {
                        startActivity(
                            Intent(
                                Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                                Uri.parse("package:$packageName"),
                            ),
                        )
                    }
                    result.success(true)
                }

                else -> result.notImplemented()
            }
        }
    }
}
