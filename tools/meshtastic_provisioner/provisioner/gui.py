"""Tkinter desktop UI for the Aervyx Meshtastic provisioner."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, APP_VERSION
from .meshtastic_io import DeviceInfo, SettingComparison, apply_target, compare_target_changes, evaluate_readback, read_device_snapshot, scan_devices
from .profiles import build_target_config, load_profile_bundle, load_saved_profile_bundle, matrix_label, profile_settings, required_placeholders, save_profile_bundle, user_profile_path
from .schema import MATRIX_ROWS, POSITION_FLAGS, PROFILE_KEYS, PROFILE_LABELS, format_position_flags, get_path, set_path


@dataclass
class DeviceRow:
    frame: ttk.Frame
    selected: tk.BooleanVar
    profile: tk.StringVar
    long_name: tk.StringVar
    short_name: tk.StringVar
    device: DeviceInfo


@dataclass
class ApplyDevicePlan:
    row: DeviceRow
    target: dict[str, Any]
    comparisons: list[SettingComparison]


SETTING_LABELS = {"owner": "Name", "owner_short": "Shortname"}
SETTING_LABELS.update({row.path: row.label for row in MATRIX_ROWS})


def setting_label(path: str) -> str:
    return SETTING_LABELS.get(path, path)


def format_review_value(path: str, value: Any) -> str:
    if value is None:
        return ""
    if path.endswith("position_flags"):
        return format_position_flags(int(value or 0))
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


class ProvisionerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1180x760")
        self.minsize(1000, 650)
        self.bundle = load_profile_bundle()
        self.matrix_path = user_profile_path()
        self.matrix_path_var = tk.StringVar(value=f"Saves to: {self.matrix_path}")
        self.rows: list[DeviceRow] = []
        self.matrix_vars: dict[tuple[str, str], tk.Variable] = {}
        self.matrix_label_vars: dict[str, tk.StringVar] = {}
        self.flag_buttons: dict[tuple[str, str], ttk.Button] = {}
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._build_ui()
        self.after(100, self._drain_log_queue)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(10, 10, 10, 6))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(3, weight=1)

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
        self.matrix_tab.rowconfigure(1, weight=0)
        self.matrix_tab.rowconfigure(2, weight=1)

        for child in self.matrix_tab.winfo_children():
            child.destroy()
        self.matrix_vars.clear()
        self.matrix_label_vars.clear()
        self.flag_buttons.clear()

        toolbar = ttk.Frame(self.matrix_tab)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(4, weight=1)
        ttk.Button(toolbar, text="Save Profile Matrix", command=self._save_matrix).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(toolbar, text="Reload Saved Matrix", command=self._reload_matrix).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(toolbar, text="Load Matrix File...", command=self._load_matrix_file).grid(row=0, column=2, padx=(0, 8))
        self.matrix_path_var.set(f"Saves to: {self.matrix_path}")
        ttk.Label(toolbar, textvariable=self.matrix_path_var).grid(row=0, column=3, sticky="w")

        header_canvas = tk.Canvas(self.matrix_tab, highlightthickness=0, height=30)
        body_canvas = tk.Canvas(self.matrix_tab, highlightthickness=0)
        vsb = ttk.Scrollbar(self.matrix_tab, orient="vertical", command=body_canvas.yview)
        hsb = ttk.Scrollbar(self.matrix_tab, orient="horizontal")
        hsb.configure(command=lambda *args: self._scroll_matrix_x(header_canvas, body_canvas, *args))
        body_canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        header_canvas.grid(row=1, column=0, sticky="ew")
        body_canvas.grid(row=2, column=0, sticky="nsew")
        vsb.grid(row=2, column=1, sticky="ns")
        hsb.grid(row=3, column=0, sticky="ew")

        header = ttk.Frame(header_canvas)
        grid = ttk.Frame(body_canvas)
        header_canvas.create_window((0, 0), window=header, anchor="nw")
        body_canvas.create_window((0, 0), window=grid, anchor="nw")
        header.bind("<Configure>", lambda event: self._configure_matrix_header(header_canvas, event))
        grid.bind("<Configure>", lambda _event: body_canvas.configure(scrollregion=body_canvas.bbox("all")))

        ttk.Label(header, text="Setting", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="ew", padx=4, pady=3)
        for column, key in enumerate(PROFILE_KEYS, start=1):
            ttk.Label(header, text=PROFILE_LABELS[key], font=("Segoe UI", 9, "bold")).grid(row=0, column=column, sticky="ew", padx=4, pady=3)
            header.columnconfigure(column, minsize=170)
            grid.columnconfigure(column, minsize=170)
        header.columnconfigure(0, minsize=245)
        grid.columnconfigure(0, minsize=245)

        last_group = None
        grid_row = 0
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
            label_var = tk.StringVar(value=matrix_label(self.bundle, row.path, row.label))
            self.matrix_label_vars[row.path] = label_var
            ttk.Entry(grid, textvariable=label_var, width=30).grid(row=grid_row, column=0, sticky="ew", padx=4, pady=2)
            for column, profile_key in enumerate(PROFILE_KEYS, start=1):
                self._make_matrix_cell(grid, grid_row, column, profile_key, row)
            grid_row += 1
        self._bind_matrix_mousewheel(header_canvas, body_canvas)
        self._bind_matrix_mousewheel(header, body_canvas)
        self._bind_matrix_mousewheel(body_canvas, body_canvas)
        self._bind_matrix_mousewheel(grid, body_canvas)

    def _configure_matrix_header(self, canvas: tk.Canvas, event: tk.Event) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"), height=event.height + 2)

    def _scroll_matrix_x(self, header_canvas: tk.Canvas, body_canvas: tk.Canvas, *args: Any) -> None:
        header_canvas.xview(*args)
        body_canvas.xview(*args)

    def _bind_matrix_mousewheel(self, widget: tk.Widget, canvas: tk.Canvas) -> None:
        widget.bind("<MouseWheel>", lambda event: self._scroll_matrix(canvas, event), add="+")
        widget.bind("<Button-4>", lambda event: self._scroll_matrix(canvas, event), add="+")
        widget.bind("<Button-5>", lambda event: self._scroll_matrix(canvas, event), add="+")
        for child in widget.winfo_children():
            self._bind_matrix_mousewheel(child, canvas)

    def _scroll_matrix(self, canvas: tk.Canvas, event: tk.Event) -> str:
        if getattr(event, "num", None) == 4:
            units = -3
        elif getattr(event, "num", None) == 5:
            units = 3
        else:
            delta = getattr(event, "delta", 0)
            units = -1 * int(delta / 120) if delta else 0
            if units == 0 and delta:
                units = -1 if delta > 0 else 1
        if units:
            canvas.yview_scroll(units, "units")
        return "break"

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
            label_overrides: dict[str, str] = {}
            for profile_key in PROFILE_KEYS:
                settings = profile_settings(next_bundle, profile_key)
                for row in MATRIX_ROWS:
                    var = self.matrix_vars[(profile_key, row.path)]
                    set_path(settings, row.path, self._matrix_value(row.kind, var.get(), row.path))
                next_bundle["profiles"][profile_key]["settings"] = settings
            for row in MATRIX_ROWS:
                label = self.matrix_label_vars[row.path].get().strip()
                if label and label != row.label:
                    label_overrides[row.path] = label
            if label_overrides:
                next_bundle["matrix_labels"] = label_overrides
            else:
                next_bundle.pop("matrix_labels", None)
            path = save_profile_bundle(next_bundle, self.matrix_path)
            self.bundle = next_bundle
            self.matrix_path = path
            self.matrix_path_var.set(f"Saves to: {self.matrix_path}")
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
            self.bundle = load_saved_profile_bundle(self.matrix_path)
            self._build_matrix_tab()
            self._log(f"Reloaded saved profile matrix from {self.matrix_path}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def _load_matrix_file(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Load Saved Profile Matrix",
            filetypes=(("YAML files", "*.yaml *.yml"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            path = Path(selected)
            self.bundle = load_saved_profile_bundle(path)
            self.matrix_path = path
            self._build_matrix_tab()
            self._log(f"Loaded saved profile matrix from {path}")
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
        plans: list[ApplyDevicePlan] = []
        try:
            self.configure(cursor="watch")
            self.update_idletasks()
            for row in selected_rows:
                target = build_target_config(self.bundle, row.profile.get(), row.long_name.get(), row.short_name.get())
                missing = required_placeholders(target)
                if missing:
                    raise ValueError(
                        "The bundled profile still has required placeholder values. "
                        "Inject a local aervyx_profiles.local.yaml before applying.\n\n"
                        + "\n".join(missing)
                    )
                self._log(f"{row.device.port}: reading current settings for review")
                current = read_device_snapshot(row.device.port)
                comparisons = compare_target_changes(current, target)
                plans.append(ApplyDevicePlan(row=row, target=target, comparisons=comparisons))
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        finally:
            self.configure(cursor="")
        plans = [plan for plan in plans if plan.comparisons]
        if not plans:
            messagebox.showinfo(APP_NAME, "Selected devices already match their revised profile settings.")
            return
        ApplyReviewDialog(self, plans)

    def _start_apply_review(self, dialog: "ApplyReviewDialog") -> None:
        dialog.set_running()
        threading.Thread(target=self._apply_review_worker, args=(dialog, dialog.plans), daemon=True).start()

    def _apply_review_worker(self, dialog: "ApplyReviewDialog", plans: list[ApplyDevicePlan]) -> None:
        for plan in plans:
            row = plan.row
            port = row.device.port
            self.after(0, lambda p=port: dialog.mark_device_pending(p))
            try:
                self._log_threadsafe(f"{port}: applying {row.profile.get()} profile")
                findings = apply_target(port, plan.target, log=self._log_threadsafe)
                if findings:
                    self._log_threadsafe(f"{port}: verification findings: {findings}")
                actual = read_device_snapshot(port)
                results = evaluate_readback(plan.comparisons, actual)
                self.after(0, lambda p=port, r=results: dialog.update_results(p, r))
            except Exception as exc:
                self._log_threadsafe(f"{port}: failed: {exc}")
                try:
                    actual = read_device_snapshot(port)
                    results = evaluate_readback(plan.comparisons, actual)
                    self.after(0, lambda p=port, r=results, e=str(exc): dialog.update_results(p, r, e))
                except Exception as read_exc:
                    self.after(0, lambda p=port, e=f"{exc}; readback failed: {read_exc}": dialog.mark_device_failed(p, e))
        self._log_threadsafe("Apply run complete.")
        self.after(0, dialog.mark_complete)

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


class ApplyReviewDialog(tk.Toplevel):
    def __init__(self, parent: ProvisionerApp, plans: list[ApplyDevicePlan]) -> None:
        super().__init__(parent)
        self.parent = parent
        self.plans = plans
        self.item_ids: dict[tuple[str, str], str] = {}
        self.running = False

        self.title("Review Settings")
        self.transient(parent)
        self.grab_set()
        self.geometry("1080x560")
        self.minsize(820, 420)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        device_count = len(plans)
        change_count = sum(len(plan.comparisons) for plan in plans)
        self.summary = ttk.Label(self, text=f"Review {change_count} changed setting(s) across {device_count} device(s).")
        self.summary.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))

        table_frame = ttk.Frame(self)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=12)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("device", "setting", "path", "current", "revised", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=18)
        headings = {
            "device": "Device",
            "setting": "Setting",
            "path": "Path",
            "current": "Current",
            "revised": "Revised",
            "status": "Status",
        }
        widths = {"device": 100, "setting": 170, "path": 270, "current": 165, "revised": 165, "status": 150}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w", stretch=column in {"path", "current", "revised", "status"})
        self.tree.tag_configure("ready", foreground="#4b5563")
        self.tree.tag_configure("pending", foreground="#8a5a00")
        self.tree.tag_configure("ok", foreground="#0f7a24")
        self.tree.tag_configure("error", foreground="#b00020")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        for plan in plans:
            port = plan.row.device.port
            for comparison in plan.comparisons:
                item = self.tree.insert(
                    "",
                    "end",
                    values=(
                        port,
                        setting_label(comparison.path),
                        comparison.path,
                        format_review_value(comparison.path, comparison.current),
                        format_review_value(comparison.path, comparison.revised),
                        "Ready",
                    ),
                    tags=("ready",),
                )
                self.item_ids[(port, comparison.path)] = item

        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, sticky="e", padx=12, pady=12)
        self.cancel_button = ttk.Button(buttons, text="Cancel", command=self._close_or_cancel)
        self.cancel_button.grid(row=0, column=0, padx=(0, 8))
        self.apply_button = ttk.Button(buttons, text="Apply", command=lambda: parent._start_apply_review(self))
        self.apply_button.grid(row=0, column=1)
        self.protocol("WM_DELETE_WINDOW", self._close_or_cancel)

    def set_running(self) -> None:
        self.running = True
        self.summary.configure(text="Applying settings and waiting for device readback...")
        self.apply_button.configure(state="disabled")
        self.cancel_button.configure(state="disabled")
        self.protocol("WM_DELETE_WINDOW", lambda: None)

    def mark_device_pending(self, port: str) -> None:
        if not self.winfo_exists():
            return
        for plan in self.plans:
            if plan.row.device.port != port:
                continue
            for comparison in plan.comparisons:
                item = self.item_ids.get((port, comparison.path))
                if item:
                    self._set_status(item, "Applying...", "pending")

    def update_results(self, port: str, results: list[SettingComparison], device_error: str = "") -> None:
        if not self.winfo_exists():
            return
        for result in results:
            item = self.item_ids.get((port, result.path))
            if not item:
                continue
            if result.ok:
                self._set_status(item, "OK", "ok")
            else:
                status = f"Error: {format_review_value(result.path, result.actual)}"
                if device_error:
                    status = f"{status} ({device_error})"
                self._set_status(item, status, "error")

    def mark_device_failed(self, port: str, error: str) -> None:
        if not self.winfo_exists():
            return
        for plan in self.plans:
            if plan.row.device.port != port:
                continue
            for comparison in plan.comparisons:
                item = self.item_ids.get((port, comparison.path))
                if item:
                    self._set_status(item, f"Error: {error}", "error")

    def mark_complete(self) -> None:
        if not self.winfo_exists():
            return
        self.running = False
        self.summary.configure(text="Apply run complete. Review the status column before closing.")
        self.cancel_button.configure(text="Close", state="normal")
        self.protocol("WM_DELETE_WINDOW", self._close_or_cancel)

    def _set_status(self, item: str, status: str, tag: str) -> None:
        values = list(self.tree.item(item, "values"))
        values[-1] = status
        self.tree.item(item, values=values, tags=(tag,))

    def _close_or_cancel(self) -> None:
        if self.running:
            return
        self.grab_release()
        self.destroy()
