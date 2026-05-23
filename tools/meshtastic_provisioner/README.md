# Aervyx Meshtastic Provisioner

Windows desktop GUI for provisioning Aervyx Meshtastic devices without using the
CLI directly.

## Run From Source

```powershell
cd tools\meshtastic_provisioner
python -m pip install -r requirements.txt
python -m provisioner
```

The app scans all COM ports, shows connected Meshtastic radios when readable,
lets you edit and save the profile matrix, and applies a selected profile after
the operator enters only the device name and shortname.

## Fleet Secrets

Tracked files contain defaults and required placeholders only. Put real MQTT,
Wi-Fi, and custom channel values in `profiles\aervyx_profiles.local.yaml` or set
`AERVYX_PROVISIONER_PROFILE` to an overlay YAML path. The build script injects
that local overlay into the packaged EXE when present.

## Build EXE

```powershell
.\build_windows.ps1
```

The output is `dist\AervyxMeshtasticProvisioner-0.1.1-win-x64.zip`. If the
overlay contains fleet secrets, distribute it only through the admin-only
provisioner release endpoint.
