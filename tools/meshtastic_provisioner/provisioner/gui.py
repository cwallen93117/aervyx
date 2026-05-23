"""Tkinter desktop UI for the Aervyx Meshtastic provisioner."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from tkinter import messagebox, ttk

from . import APP_NAME, APP_VERSION
from .meshtastic_io import DeviceInfo, apply_target, scan_devices
from .profiles import build_target_config, load_profile_bundle, profile_settings, required_placeholders, save_profile_bundle, user_profile_path
from .schema import MATRIX_ROWS, POSITION_FLAGS, PROFILE_KEYS, PROFILE_LABELS, format_position_flags, get_path, set_path


@dataclass
class DeviceRow:
    frame: ttk.Frame
    selected: tk.BooleanVar
    profile: tk.StringVar
    long_name: tk.StringVar
    short_name: tk.StringVar
    device: DeviceInfo


class ProvisionerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1180x760")
        self.minsize(1000, 650)
        self.bundle = load_profile_bundle()
        self.rows: list[DeviceRow] = []
        self.matrix_vars: dict[tuple[str, str], tk.Variable] = {}
        self.flag_buttons: dict[tuple[str, str], ttk.Button] = {}
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._build_ui()
        self.after(100, self._drain_log_queue)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(10, 10, 10, 6))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(4, weight=1)

        ttk.Button(toolbar, text="Scan COM Ports", command=self.scan).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(toolbar, text="Apply Selected", command=self.apply_selected).grid(row=0, column=1, padx=(0, 8))
        ttk.Label(toolbar, text="Only Name and Shortname are entered here; all other settings come from the selected profile.").grid(row=0, column=2, sticky="w")

        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.devices_tab = ttk.Frame(notebook, padding=8)
        self.matrix_tab = ttk.Frame(notebook, padding=8)
        self.log_tab = ttk.Frame(notebook, padding=8)
        notebook.add(self.devices_tab, text="Provision Devices")
        notebook.add(self.matrix_tab, text="Profile Matrix")
        notebook.add(self.log_tab, text="Log")

        self._build_devices_tab()
        self._build_matrix_tab()
        self._build_log_tab()

    def _build_devices_tab(self) -> None:
        self.devices_tab.columnconfigure(0, weight=1)
        self.devices_tab.rowconfigure(1, weight=1)
        header = ttk.Frame(self.devices_tab)
        header.grid(row=0, column=0, sticky="ew")
        headings = ["Use", "COM", "Detected Device", "Node ID", "Firmware", "Profile", "Name", "Shortname", "MQTT/Channel"]
        widths = [5, 8, 24, 12, 18, 16, 22, 10, 30]
        for col, (heading, width) in enumerate(zip(headings, widths)):
            header.columnconfigure(col, weight=1 if col in {2, 8} else 0, minsize=width * 8)
            ttk.Label(header, text=heading, font=("Segoe UI", 9, "bold")).grid(row=0, column=col, sticky="w", padx=4)

        self.device_container = ttk.Frame(self.devices_tab)
        self.device_container.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.device_container.columnconfigure(0, weight=1)
        ttk.Label(self.device_container, text="Click Scan COM Ports to find connected Meshtastic devices.").grid(row=0, column=0, sticky="w", padx=4, pady=10)

    def _build_matrix_tab(self) -> None:
        self.matrix_tab.columnconfigure(0, weight=1)
        self.matrix_tab.rowconfigure(1, weight=1)

        for child in self.matrix_tab.winfo_children():
            child.destroy()
        self.matrix_vars.clear()
        self.flag_buttons.clear()

        toolbar = ttk.Frame(self.matrix_tab)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(3, weight=1)
        ttk.Button(toolbar, text="Save Profile Matrix", command=self._save_matrix).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(toolbar, text="Reload Saved Matrix", command=self._reload_matrix).grid(row=0, column=1, padx=(0, 8))
        ttk.Label(toolbar, text=f"Saves to: {user_profile_path()}").grid(row=0, column=2, sticky="w")

        canvas = tk.Canvas(self.matrix_tab, highlightthickness=0)
        vsb = ttk.Scrollbar(self.matrix_tab, orient="vertical", command=canvas.yview)
        hsb = ttk.Scrollbar(self.matrix_tab, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        vsb.grid(row=1, column=1, sticky="ns")
        hsb.grid(row=2, column=0, sticky="ew")

        grid = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=grid, anchor="nw")
        grid.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))

        ttk.Label(grid, text="Setting", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="ew", padx=4, pady=3)
        for column, key in enumerate(PROFILE_KEYS, start=1):
            ttk.Label(grid, text=PROFILE_LABELS[key], font=("Segoe UI", 9, "bold")).grid(row=0, column=column, sticky="ew", padx=4, pady=3)
            grid.columnconfigure(column, minsize=170)
        grid.columnconfigure(0, minsize=245)

        last_group = None
        grid_row = 1
        for row in MATRIX_ROWS:
            if row.group != last_group:
                ttk.Label(grid, text=row.group, font=("Segoe UI", 9, "bold"), background="#e8eef7").grid(
                    row=grid_row,
                    column=0,
                    columnspan=len(PROFILE_KEYS) + 1,
                    sticky="ew",
                    padx=2,
                    pady=(8, 2),
                )
                last_group = row.group
                grid_row += 1
            ttk.Label(grid, text=row.label).grid(row=grid_row, column=0, sticky="w", padx=4, pady=2)
            for column, profile_key in enumerate(PROFILE_KEYS, start=1):
                self._make_matrix_cell(grid, grid_row, column, profile_key, row)
            grid_row += 1

    def _make_matrix_cell(self, parent: ttk.Frame, grid_row: int, column: int, profile_key: str, row) -> None:
        value = get_path(profile_settings(self.bundle, profile_key), row.path, "")
        key = (profile_key, row.path)
        if row.kind == "boolean":
            var = tk.BooleanVar(value=bool(value))
            self.matrix_vars[key] = var
            ttk.Checkbutton(parent, variable=var).grid(row=grid_row, column=column, padx=4, pady=2)
        elif row.kind == "flags":
            var = tk.IntVar(value=int(value or 0))
            self.matrix_vars[key] = var
            button = ttk.Button(parent, text=format_position_flags(var.get()), command=lambda pk=profile_key, r=row, v=var: self._open_flags_editor(pk, r, v))
            button.grid(row=grid_row, column=column, sticky="ew", padx=4, pady=2)
            self.flag_buttons[key] = button
        else:
            var = tk.StringVar(value="" if value is None else str(value))
            self.matrix_vars[key] = var
            if row.options:
                ttk.Combobox(parent, textvariable=var, values=list(row.options), state="readonly", width=18).grid(row=grid_row, column=column, sticky="ew", padx=4, pady=2)
            else:
                ttk.Entry(parent, textvariable=var, width=22).grid(row=grid_row, column=column, sticky="ew", padx=4, pady=2)

    def _open_flags_editor(self, profile_key: str, row, var: tk.IntVar) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(f"{PROFILE_LABELS[profile_key]} Position Flags")
        dialog.transient(self)
        dialog.grab_set()
        checks: list[tuple[int, tk.BooleanVar]] = []
        ttk.Label(dialog, text="Select fields included in outgoing position packets.").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        current = int(var.get())
        for idx, (bit, label) in enumerate(POSITION_FLAGS, start=1):
            check_var = tk.BooleanVar(value=(current & bit) != 0)
            checks.append((bit, check_var))
            ttk.Checkbutton(dialog, text=label, variable=check_var).grid(row=idx, column=0, sticky="w", padx=12, pady=2)

        def save_flags() -> None:
            mask = 0
            for bit, check_var in checks:
                if check_var.get():
                    mask |= bit
            var.set(mask)
            button = self.flag_buttons.get((profile_key, row.path))
            if button:
                button.configure(text=format_position_flags(mask))
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.grid(row=len(POSITION_FLAGS) + 1, column=0, sticky="e", padx=12, pady=12)
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Save", command=save_flags).grid(row=0, column=1)

    def _save_matrix(self) -> None:
        try:
            next_bundle = deepcopy(self.bundle)
            for profile_key in PROFILE_KEYS:
                settings = profile_settings(next_bundle, profile_key)
                for row in MATRIX_ROWS:
                    var = self.matrix_vars[(profile_key, row.path)]
                    set_path(settings, row.path, self._matrix_value(row.kind, var.get(), row.path))
                next_bundle["profiles"][profile_key]["settings"] = settings
            path = save_profile_bundle(next_bundle)
            self.bundle = next_bundle
            self._log(f"Saved profile matrix to {path}")
            messagebox.showinfo(APP_NAME, f"Saved profile matrix to:\n{path}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def _matrix_value(self, kind: str, value: Any, path: str) -> Any:
        if kind == "boolean":
            return bool(value)
        if kind == "number" or kind == "flags":
            text = str(value).strip()
            return int(text or 0)
        return str(value)

    def _reload_matrix(self) -> None:
        try:
            self.bundle = load_profile_bundle()
            self._build_matrix_tab()
            self._log("Reloaded profile matrix.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def _build_log_tab(self) -> None:
        self.log_tab.columnconfigure(0, weight=1)
        self.log_tab.rowconfigure(0, weight=1)
        self.log_text = tk.Text(self.log_tab, wrap="word", height=12)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        ttk.Scrollbar(self.log_tab, orient="vertical", command=self.log_text.yview).grid(row=0, column=1, sticky="ns")

    def scan(self) -> None:
        self._log("Starting COM scan...")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self) -> None:
        try:
            devices = scan_devices(log=self._log_threadsafe)
            self.after(0, lambda: self._render_devices(devices))
            self._log_threadsafe(f"Scan complete: {len(devices)} candidate device(s).")
        except Exception as exc:
            self._log_threadsafe(f"Scan failed: {exc}")

    def _render_devices(self, devices: list[DeviceInfo]) -> None:
        for child in self.device_container.winfo_children():
            child.destroy()
        self.rows.clear()
        if not devices:
            ttk.Label(self.device_container, text="No Meshtastic devices found.").grid(row=0, column=0, sticky="w", padx=4, pady=10)
            return
        for index, device in enumerate(devices):
            row_frame = ttk.Frame(self.device_container)
            row_frame.grid(row=index, column=0, sticky="ew", pady=2)
            for col in range(9):
                row_frame.columnconfigure(col, weight=1 if col in {2, 8} else 0)
            selected = tk.BooleanVar(value=device.status == "Ready")
            profile = tk.StringVar(value="pilot")
            long_name = tk.StringVar(value=device.long_name)
            short_name = tk.StringVar(value=device.short_name)
            ttk.Checkbutton(row_frame, variable=selected).grid(row=0, column=0, sticky="w", padx=4)
            ttk.Label(row_frame, text=device.port).grid(row=0, column=1, sticky="w", padx=4)
            detected = f"{device.long_name or device.usb_description} {device.short_name}".strip()
            if device.status != "Ready":
                detected = f"{device.status}: {device.error or device.usb_description}"
            ttk.Label(row_frame, text=detected).grid(row=0, column=2, sticky="ew", padx=4)
            ttk.Label(row_frame, text=device.node_id).grid(row=0, column=3, sticky="w", padx=4)
            ttk.Label(row_frame, text=device.firmware).grid(row=0, column=4, sticky="w", padx=4)
            ttk.Combobox(row_frame, textvariable=profile, values=list(PROFILE_KEYS), width=14, state="readonly").grid(row=0, column=5, sticky="ew", padx=4)
            ttk.Entry(row_frame, textvariable=long_name, width=22).grid(row=0, column=6, sticky="ew", padx=4)
            ttk.Entry(row_frame, textvariable=short_name, width=8).grid(row=0, column=7, sticky="ew", padx=4)
            status = f"MQTT {device.mqtt_address or '-'} | proxy {'on' if device.mqtt_proxy else 'off'} | PSK {device.channel_psk}"
            ttk.Label(row_frame, text=status).grid(row=0, column=8, sticky="ew", padx=4)
            self.rows.append(DeviceRow(row_frame, selected, profile, long_name, short_name, device))

    def apply_selected(self) -> None:
        selected_rows = [row for row in self.rows if row.selected.get() and row.device.status == "Ready"]
        if not selected_rows:
            messagebox.showinfo(APP_NAME, "Select at least one ready device.")
            return
        try:
            for row in selected_rows:
                target = build_target_config(self.bundle, row.profile.get(), row.long_name.get(), row.short_name.get())
                missing = required_placeholders(target)
                if missing:
                    raise ValueError(
                        "The bundled profile still has required placeholder values. "
                        "Inject a local aervyx_profiles.local.yaml before applying.\n\n"
                        + "\n".join(missing)
                    )
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        if not messagebox.askyesno(APP_NAME, f"Apply profiles to {len(selected_rows)} device(s)?"):
            return
        threading.Thread(target=self._apply_worker, args=(selected_rows,), daemon=True).start()

    def _apply_worker(self, rows: list[DeviceRow]) -> None:
        for row in rows:
            try:
                target = build_target_config(self.bundle, row.profile.get(), row.long_name.get(), row.short_name.get())
                self._log_threadsafe(f"{row.device.port}: applying {row.profile.get()} profile")
                findings = apply_target(row.device.port, target, log=self._log_threadsafe)
                if findings:
                    self._log_threadsafe(f"{row.device.port}: verification findings: {findings}")
            except Exception as exc:
                self._log_threadsafe(f"{row.device.port}: failed: {exc}")
        self._log_threadsafe("Apply run complete.")

    def _log(self, message: str) -> None:
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")

    def _log_threadsafe(self, message: str) -> None:
        self.log_queue.put(message)

    def _drain_log_queue(self) -> None:
        try:
            while True:
                self._log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._drain_log_queue)


def main() -> None:
    app = ProvisionerApp()
    app.mainloop()
