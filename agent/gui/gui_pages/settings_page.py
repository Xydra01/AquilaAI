"""Runtime settings: Ollama engines, aquila model picker, SearXNG."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QListWidget,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from agent.core import apply_runtime_settings, client
from agent.aquila_runtime.hardware_profile import detect_hardware_profile
from agent.aquila_runtime.setup_health import collect_setup_health
from agent.research import (
    docker_status,
    probe_health,
    start_search,
    stop_search,
    update_search_settings,
)
from agent.storage import (
    catalog_sections_for_gui,
    export_env_on_save,
    load_app_mcp_servers,
    load_preferences,
    load_runtime_settings,
    model_available_on_engine,
    prefer_model_for_engine,
    resolve_model_tag,
    save_app_mcp_servers,
    save_preferences,
    save_runtime_settings,
    set_engine,
    set_export_env_on_save,
)
import remote.server_control as server_control
from remote.server_control import ENGINES, tail_log

from .settings_catalog_ui import PreferenceWidgets
from ..gui_theme import settings_panel_stylesheet


class _HealthWorker(QThread):
    finished_signal = Signal(dict)

    def run(self) -> None:
        try:
            self.finished_signal.emit(collect_setup_health())
        except Exception as exc:
            self.finished_signal.emit({"error": str(exc)})


class _EngineWorker(QThread):
    finished_signal = Signal(dict)

    def __init__(
        self,
        action: str,
        engine: str = "",
        stop_other: bool = False,
        base_url: str = "",
    ):
        super().__init__()
        self.action = action
        self.engine = engine
        self.stop_other = stop_other
        self.base_url = base_url

    def run(self) -> None:
        try:
            if self.action == "status":
                self.finished_signal.emit(
                    {"ok": True, "engines": server_control.engine_status()}
                )
            elif self.action == "start":
                self.finished_signal.emit(
                    server_control.start_engine(self.engine, stop_other=self.stop_other)
                )
            elif self.action == "stop":
                self.finished_signal.emit(server_control.stop_engine(self.engine))
            elif self.action == "warmup":
                base = server_control.ENGINES[self.engine]["base_url"]
                self.finished_signal.emit(server_control.warmup_model(base_url=base))
            elif self.action == "eject":
                base = server_control.ENGINES[self.engine]["base_url"]
                self.finished_signal.emit(
                    server_control.eject_model(base_url=base, all_loaded=True)
                )
            elif self.action == "logs":
                self.finished_signal.emit(
                    {
                        "ok": True,
                        "text": server_control.tail_log(self.engine, 200),
                        "engine": self.engine,
                    }
                )
            elif self.action == "models":
                detail = client.discover_aquila_models(
                    primary_base_url=self.base_url or None
                )
                self.finished_signal.emit(
                    {
                        "ok": True,
                        "engine": self.engine,
                        "models": detail.get("models") or [],
                        "error": detail.get("error"),
                        "base_url": detail.get("base_url"),
                    }
                )
            else:
                self.finished_signal.emit({"ok": False, "message": "unknown action"})
        except Exception as exc:
            self.finished_signal.emit({"ok": False, "message": str(exc)})


class SettingsPage(QWidget):
    """Configure Ollama engines, active aquila model, and SearXNG."""

    settings_applied = Signal()

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._worker: _EngineWorker | None = None
        self._models_worker: _EngineWorker | None = None
        self._health_worker: _HealthWorker | None = None
        self._model_preselect: str = ""
        self._engine_cards: dict[str, dict] = {}
        self._pending_start_engine: str | None = None
        self._catalog_widgets: dict[str, PreferenceWidgets] = {}
        self._nav_labels: list[str] = []
        self._nav_section_ids: list[str | None] = []
        self._panel_widgets: list[QWidget] = []
        self._health_labels: dict[str, QLabel] = {}

        root = QVBoxLayout(self)
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(title)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search settings:"))
        self.settings_search = QLineEdit()
        self.settings_search.setPlaceholderText("Filter by name or AQUILA_* key…")
        self.settings_search.textChanged.connect(self._filter_settings_nav)
        search_row.addWidget(self.settings_search, stretch=1)
        root.addLayout(search_row)

        self.splitter = QSplitter()
        root.addWidget(self.splitter, stretch=1)

        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(200)
        self.splitter.addWidget(self.nav_list)

        self.stacked = QStackedWidget()
        self.splitter.addWidget(self.stacked)

        self._build_get_started_page()
        self._build_catalog_pages()
        self._build_custom_ui()
        self._build_email_page()
        self._build_logs_page()

        self.nav_list.currentRowChanged.connect(self.stacked.setCurrentIndex)
        if self.nav_list.count() > 0:
            self.nav_list.setCurrentRow(0)

        self._build_engine_cards()
        self.load_from_settings()
        self.refresh_theme(dark=getattr(main_window, "dark_mode", False))

    def _track_panel(self, widget: QWidget) -> QWidget:
        widget.setProperty("aquilaPanel", True)
        self._panel_widgets.append(widget)
        return widget

    def _make_settings_scroll(self) -> tuple[QScrollArea, QWidget]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = self._track_panel(QWidget())
        scroll.setWidget(content)
        return scroll, content

    def refresh_theme(self, *, dark: bool) -> None:
        self.setStyleSheet(settings_panel_stylesheet(dark=dark))
        for widget in self._panel_widgets:
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _build_get_started_page(self) -> None:
        page = self._track_panel(QWidget())
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(
                "Quick health check for your Aquila install. "
                "Use AI Engine below to start Ollama and pick a model."
            )
        )
        box = QGroupBox("Status")
        form = QFormLayout(box)
        for key, label in (
            ("hardware", "Hardware"),
            ("ollama", "Ollama"),
            ("model", "Model"),
            ("search", "Web search"),
            ("docker", "Docker"),
        ):
            lbl = QLabel("…")
            lbl.setWordWrap(True)
            self._health_labels[key] = lbl
            form.addRow(label, lbl)
        layout.addWidget(box)
        refresh = QPushButton("Refresh status")
        refresh.clicked.connect(self._refresh_health)
        layout.addWidget(refresh)
        layout.addStretch()
        self._add_nav_item("Get Started")
        self.stacked.addWidget(page)

    def _refresh_health(self) -> None:
        self._refresh_health_async()

    def _refresh_health_async(self) -> None:
        if self._health_worker and self._health_worker.isRunning():
            return
        self._health_worker = _HealthWorker()
        self._health_worker.finished_signal.connect(self._apply_health)
        self._health_worker.start()

    def _apply_health(self, health: dict) -> None:
        if health.get("error"):
            self._health_labels["hardware"].setText(
                f"Health check failed: {health['error']}"
            )
            return
        profile = health["profile"]
        self._health_labels["hardware"].setText(
            f"{profile.label}"
            + (f" — {profile.performance_note}" if profile.performance_note else "")
        )
        self._health_labels["ollama"].setText(
            "Running" if health["ollama_running"] else "Not running — start in AI Engine"
        )
        self._health_labels["model"].setText(
            "Ready" if health["model_ready"] else health["model_message"]
        )
        self._health_labels["search"].setText(
            health["search_message"]
            if health["search_ok"]
            else f"Optional: {health['search_message']}"
        )
        docker_msg = health["docker_message"] or (
            "running" if health["docker_running"] else "not running"
        )
        if not health["docker_available"]:
            docker_msg = health["docker_message"] or "Docker not installed (web search optional)"
        self._health_labels["docker"].setText(docker_msg)
        self._refresh_search_docker_status()

    def _build_email_page(self) -> None:
        from agent.storage.config_catalog import load_catalog

        page = self._track_panel(QWidget())
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Email tool (optional). Leave blank if you do not use send_email."))
        scroll, content = self._make_settings_scroll()
        form = QFormLayout(content)
        smtp_section = next(s for s in load_catalog() if s.id == "email_smtp")
        widgets = PreferenceWidgets()
        widgets.add_section(form, smtp_section)
        self._catalog_widgets["email_smtp"] = widgets
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.export_env_check = QCheckBox("Also update .env for shell scripts")
        self.export_env_check.setChecked(export_env_on_save())
        self.export_env_check.toggled.connect(
            lambda checked: set_export_env_on_save(checked)
        )
        layout.addWidget(self.export_env_check)
        save_btn = QPushButton("Save email settings")
        save_btn.clicked.connect(lambda: self._save_catalog_section("email_smtp"))
        layout.addWidget(save_btn)
        layout.addStretch()
        self._add_nav_item("Email", "email_smtp")
        self.stacked.addWidget(page)

    def _build_catalog_pages(self) -> None:
        tier1 = [s for s in catalog_sections_for_gui(include_advanced=False) if s.tier == 1]
        tier2 = [s for s in catalog_sections_for_gui(include_advanced=True) if s.tier > 1]
        chat_first = sorted(
            tier1,
            key=lambda s: (0 if s.id == "chat_light_research" else 1, s.title),
        )
        for section in chat_first + tier2:
            self._add_catalog_section_page(section)

    def _add_catalog_section_page(self, section) -> None:
        page = self._track_panel(QWidget())
        layout = QVBoxLayout(page)
        header = QLabel(section.title)
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header)
        scroll, content = self._make_settings_scroll()
        form = QFormLayout(content)
        widgets = PreferenceWidgets()
        widgets.add_section(form, section)
        self._catalog_widgets[section.id] = widgets
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)
        export_row = QHBoxLayout()
        export_chk = QCheckBox("Also update .env for shell scripts")
        export_chk.setChecked(export_env_on_save())
        export_chk.toggled.connect(lambda checked, s=section.id: self._on_export_toggle(checked))
        export_row.addWidget(export_chk)
        export_row.addStretch()
        layout.addLayout(export_row)
        save_btn = QPushButton(f"Save {section.title}")
        save_btn.clicked.connect(lambda _=False, sid=section.id: self._save_catalog_section(sid))
        layout.addWidget(save_btn)
        self._add_nav_item(section.title, section.id)
        self.stacked.addWidget(page)

    def _on_export_toggle(self, checked: bool) -> None:
        set_export_env_on_save(checked)
        if hasattr(self, "export_env_check"):
            self.export_env_check.blockSignals(True)
            self.export_env_check.setChecked(checked)
            self.export_env_check.blockSignals(False)

    def _add_nav_item(self, label: str, section_id: str | None = None) -> None:
        self._nav_labels.append(label)
        self._nav_section_ids.append(section_id)
        self.nav_list.addItem(label)

    def _filter_settings_nav(self, text: str) -> None:
        q = text.strip().lower()
        for row in range(self.nav_list.count()):
            label = self._nav_labels[row] if row < len(self._nav_labels) else ""
            show = not q or q in label.lower()
            if not show and q:
                section_id = (
                    self._nav_section_ids[row]
                    if row < len(self._nav_section_ids)
                    else None
                )
                widgets = self._catalog_widgets.get(section_id or "")
                if widgets:
                    show = bool(widgets.filter_text(q))
            self.nav_list.item(row).setHidden(not show)

    def _save_catalog_section(self, section_id: str) -> None:
        widgets = self._catalog_widgets.get(section_id)
        if not widgets:
            return
        try:
            save_preferences(
                widgets.collect_updates(),
                export_env=export_env_on_save(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Settings", str(exc))
            return
        apply_runtime_settings()
        self.settings_applied.emit()
        QMessageBox.information(self, "Settings", "Saved and applied.")

    def _build_logs_page(self) -> None:
        logs_page = self._track_panel(QWidget())
        logs_layout = QVBoxLayout(logs_page)
        logs_box = QGroupBox("Engine logs")
        llayout = QVBoxLayout(logs_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        llayout.addWidget(self.log_view)
        logs_layout.addWidget(logs_box, stretch=1)
        self._add_nav_item("Logs")
        self.stacked.addWidget(logs_page)

    def _save_email_settings(self) -> None:
        self._save_catalog_section("email_smtp")

    def _build_custom_ui(self):
        ollama_page = self._track_panel(QWidget())
        ollama_layout = QVBoxLayout(ollama_page)

        self.hw_profile_label = QLabel("")
        self.hw_profile_label.setWordWrap(True)
        try:
            prof = detect_hardware_profile()
            self.hw_profile_label.setText(
                f"Detected: {prof.label}"
                + (f" — {prof.performance_note}" if prof.performance_note else "")
            )
        except Exception:
            pass
        ollama_layout.addWidget(self.hw_profile_label)

        ollama_box = QGroupBox("Ollama engine")
        ob_layout = QVBoxLayout(ollama_box)
        self.engine_grid = QGridLayout()
        ob_layout.addLayout(self.engine_grid)
        refresh_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh status")
        self.refresh_btn.clicked.connect(self.refresh_engines)
        refresh_row.addWidget(self.refresh_btn)
        refresh_row.addStretch()
        ob_layout.addLayout(refresh_row)
        ollama_layout.addWidget(ollama_box)

        model_box = QGroupBox("Active model (aquila tags only)")
        model_layout = QHBoxLayout(model_box)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(280)
        self.reload_models_btn = QPushButton("Reload models")
        self.reload_models_btn.clicked.connect(self._reload_models_for_active_engine)
        self.apply_model_btn = QPushButton("Apply model")
        self.apply_model_btn.clicked.connect(self._apply_model)
        model_layout.addWidget(QLabel("Model:"))
        model_layout.addWidget(self.model_combo, stretch=1)
        model_layout.addWidget(self.reload_models_btn)
        model_layout.addWidget(self.apply_model_btn)
        ollama_layout.addWidget(model_box)
        self.model_status_label = QLabel("")
        self.model_status_label.setWordWrap(True)
        ollama_layout.addWidget(self.model_status_label)

        ctx_row = QHBoxLayout()
        ctx_row.addWidget(QLabel("num_ctx (optional):"))
        self.num_ctx_spin = QSpinBox()
        self.num_ctx_spin.setRange(0, 131072)
        self.num_ctx_spin.setSpecialValueText("default")
        self.num_ctx_spin.setValue(0)
        ctx_row.addWidget(self.num_ctx_spin)
        ctx_row.addStretch()
        ollama_layout.addLayout(ctx_row)
        ollama_layout.addStretch()

        self._add_nav_item("AI Engine")
        self.stacked.addWidget(ollama_page)

        # SearXNG
        search_page = self._track_panel(QWidget())
        search_layout = QVBoxLayout(search_page)
        search_box = QGroupBox("SearXNG search")
        slayout = QVBoxLayout(search_box)
        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("Base URL:"))
        self.search_url_input = QLineEdit()
        url_row.addWidget(self.search_url_input, stretch=1)
        slayout.addLayout(url_row)
        eng_row = QHBoxLayout()
        eng_row.addWidget(QLabel("Engines:"))
        self.search_engines_input = QLineEdit()
        eng_row.addWidget(self.search_engines_input, stretch=1)
        slayout.addLayout(eng_row)
        search_btn_row = QHBoxLayout()
        self.search_test_btn = QPushButton("Test connection")
        self.search_test_btn.clicked.connect(self._test_search)
        self.search_start_btn = QPushButton("Start container")
        self.search_start_btn.clicked.connect(self._start_search_container)
        self.search_stop_btn = QPushButton("Stop container")
        self.search_stop_btn.clicked.connect(self._stop_search_container)
        self.search_save_btn = QPushButton("Save search settings")
        self.search_save_btn.clicked.connect(self._save_search_settings)
        search_btn_row.addWidget(self.search_test_btn)
        search_btn_row.addWidget(self.search_start_btn)
        search_btn_row.addWidget(self.search_stop_btn)
        search_btn_row.addWidget(self.search_save_btn)
        slayout.addLayout(search_btn_row)
        self.search_status_label = QLabel("")
        slayout.addWidget(self.search_status_label)
        search_layout.addWidget(search_box)
        search_layout.addStretch()

        self._add_nav_item("Web Search")
        self.stacked.addWidget(search_page)

        # MCP
        mcp_page = self._track_panel(QWidget())
        mcp_layout = QVBoxLayout(mcp_page)
        mcp_box = QGroupBox("MCP servers (stdio + SSE)")
        mlayout = QVBoxLayout(mcp_box)
        mlayout.addWidget(
            QLabel(
                "JSON array of servers: name, transport (stdio|sse), command, args, "
                "env, url, enabled. Tools appear as mcp__name__tool in Autonomous mode."
            )
        )
        self.mcp_json = QPlainTextEdit()
        self.mcp_json.setPlaceholderText(
            '[{"name": "example", "transport": "stdio", "command": "npx", '
            '"args": ["-y", "@modelcontextprotocol/server-everything"], "enabled": false}]'
        )
        self.mcp_json.setMaximumBlockCount(500)
        mlayout.addWidget(self.mcp_json)
        mcp_btn_row = QHBoxLayout()
        self.mcp_save_btn = QPushButton("Save MCP servers")
        self.mcp_save_btn.clicked.connect(self._save_mcp_servers)
        self.mcp_test_btn = QPushButton("Reconnect MCP")
        self.mcp_test_btn.clicked.connect(self._reconnect_mcp)
        mcp_btn_row.addWidget(self.mcp_save_btn)
        mcp_btn_row.addWidget(self.mcp_test_btn)
        mlayout.addLayout(mcp_btn_row)
        self.mcp_status_label = QLabel("")
        mlayout.addWidget(self.mcp_status_label)
        mcp_layout.addWidget(mcp_box)
        
        self._add_nav_item("Integrations")
        self.stacked.addWidget(mcp_page)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.load_from_settings()
        self.refresh_engines()
        self._refresh_health_async()

    def load_from_settings(self) -> None:
        settings = load_runtime_settings()
        prefs = load_preferences()

        for widgets in self._catalog_widgets.values():
            widgets.load_values(prefs)

        self.search_url_input.setText(settings.searxng_base_url)
        self.search_engines_input.setText(settings.searxng_engines)
        if settings.ollama_num_ctx:
            self.num_ctx_spin.setValue(settings.ollama_num_ctx)
        else:
            self.num_ctx_spin.setValue(0)
        self._load_mcp_json()
        self._reload_models_for_active_engine(preselect=settings.ollama_model)

    def _load_mcp_json(self) -> None:
        import json as _json

        servers = load_app_mcp_servers()
        self.mcp_json.setPlainText(_json.dumps(servers, indent=2))

    def _save_mcp_servers(self) -> None:
        import json as _json

        try:
            raw = _json.loads(self.mcp_json.toPlainText() or "[]")
        except _json.JSONDecodeError as exc:
            QMessageBox.warning(self, "MCP", f"Invalid JSON: {exc}")
            return
        if not isinstance(raw, list):
            QMessageBox.warning(self, "MCP", "Root must be a JSON array.")
            return
        save_app_mcp_servers(raw)
        self._reconnect_mcp()
        QMessageBox.information(self, "MCP", "MCP server list saved.")

    def _reconnect_mcp(self) -> None:
        from agent.core import get_global_agent

        try:
            agent = get_global_agent()
            agent.refresh_mcp_tools()
            health = agent.mcp_bridge.server_health()
            lines = [
                f"{name}: {'ok' if h.get('healthy') else h.get('error') or 'offline'} "
                f"({h.get('tool_count', 0)} tools)"
                for name, h in health.items()
            ]
            self.mcp_status_label.setText("; ".join(lines) or "No MCP servers configured.")
            self.settings_applied.emit()
        except Exception as exc:
            self.mcp_status_label.setText(f"MCP reconnect failed: {exc}")

    def _build_engine_cards(self) -> None:
        for idx, engine in enumerate(("stock", "tq")):
            meta = server_control.ENGINES[engine]
            box = QGroupBox(meta["label"])
            layout = QVBoxLayout(box)
            status_lbl = QLabel("Status: …")
            url_lbl = QLabel(meta["base_url"])
            models_lbl = QLabel("Loaded: —")
            layout.addWidget(status_lbl)
            layout.addWidget(url_lbl)
            layout.addWidget(models_lbl)
            btn_row = QHBoxLayout()
            toggle_btn = QPushButton("Start")
            use_btn = QPushButton("Use engine")
            warmup_btn = QPushButton("Warm up")
            eject_btn = QPushButton("Eject")
            logs_btn = QPushButton("Logs")
            toggle_btn.clicked.connect(lambda _=False, e=engine: self._toggle_engine(e))
            use_btn.clicked.connect(lambda _=False, e=engine: self._use_engine(e))
            warmup_btn.clicked.connect(lambda _=False, e=engine: self._warmup_engine(e))
            eject_btn.clicked.connect(lambda _=False, e=engine: self._eject_engine(e))
            logs_btn.clicked.connect(lambda _=False, e=engine: self._show_logs(e))
            for btn in (toggle_btn, use_btn, warmup_btn, eject_btn, logs_btn):
                btn_row.addWidget(btn)
            layout.addLayout(btn_row)
            self.engine_grid.addWidget(box, 0, idx)
            self._engine_cards[engine] = {
                "status": status_lbl,
                "models": models_lbl,
                "toggle": toggle_btn,
            }

    def refresh_engines(self) -> None:
        self._run_worker("status")

    def _toggle_engine(self, engine: str) -> None:
        card = self._engine_cards.get(engine, {})
        is_up = card.get("toggle") and card["toggle"].text() == "Stop"
        if is_up:
            self._run_worker("stop", engine=engine)
        else:
            self._pending_start_engine = engine
            self._run_worker("start", engine=engine, stop_other=False)

    def _use_engine(self, engine: str) -> None:
        settings = load_runtime_settings()
        set_engine(settings, engine)
        settings.ollama_base_url = server_control.ENGINES[engine]["base_url"]
        save_runtime_settings(settings)
        apply_runtime_settings()
        self._reload_models_for_active_engine()
        self.settings_applied.emit()
        if self.main_window:
            self.main_window._update_instance_label()
        QMessageBox.information(
            self,
            "Engine active",
            f"Agent now targets {settings.ollama_base_url}",
        )

    def _warmup_engine(self, engine: str) -> None:
        self._run_worker("warmup", engine=engine)

    def _eject_engine(self, engine: str) -> None:
        self._run_worker("eject", engine=engine)

    def _show_logs(self, engine: str) -> None:
        self._run_worker("logs", engine=engine)

    def _reload_models_for_active_engine(self, preselect: str | None = None) -> None:
        settings = load_runtime_settings()
        self._model_preselect = preselect or ""
        if self._models_worker and self._models_worker.isRunning():
            return
        self._models_worker = _EngineWorker(
            "models",
            engine=settings.ollama_engine,
            base_url=settings.ollama_base_url,
        )
        self._models_worker.finished_signal.connect(self._on_worker_done)
        self._models_worker.start()

    def _apply_model(self) -> None:
        model = self.model_combo.currentText().strip()
        if not model or model.startswith("("):
            QMessageBox.warning(self, "Model", "Select a model first.")
            return
        settings = load_runtime_settings()
        tags = client.discover_aquila_models(
            primary_base_url=settings.ollama_base_url
        ).get("models") or []
        resolved = resolve_model_tag(model, tags) or model
        settings.ollama_model = resolved
        num_ctx = self.num_ctx_spin.value()
        settings.ollama_num_ctx = num_ctx if num_ctx > 0 else None
        save_runtime_settings(settings)
        apply_runtime_settings()
        self.settings_applied.emit()
        if self.main_window:
            self.main_window._update_instance_label()
        QMessageBox.information(self, "Model applied", f"Active model: {resolved}")

    def _test_search(self) -> None:
        update_search_settings(
            self.search_url_input.text().strip(),
            self.search_engines_input.text().strip(),
        )
        ok, msg = probe_health()
        self.search_status_label.setText(msg if ok else f"Failed: {msg}")

    def _save_search_settings(self) -> None:
        update_search_settings(
            self.search_url_input.text().strip(),
            self.search_engines_input.text().strip(),
        )
        apply_runtime_settings()
        self.settings_applied.emit()
        self.search_status_label.setText("Search settings saved and applied.")

    def _start_search_container(self) -> None:
        from agent.aquila_runtime.search_bundle import ensure_search_support_files

        ok, msg = ensure_search_support_files()
        if not ok:
            self.search_status_label.setText(msg)
            return
        ok, msg = start_search()
        self.search_status_label.setText(msg)
        self._refresh_search_docker_status()

    def _stop_search_container(self) -> None:
        ok, msg = stop_search()
        self.search_status_label.setText(msg)
        self._refresh_search_docker_status()

    def _refresh_search_docker_status(self) -> None:
        status = docker_status()
        if not status.get("available"):
            extra = status.get("message", "docker unavailable")
        elif status.get("running"):
            extra = "container running"
        else:
            extra = status.get("state") or status.get("message") or "container stopped"
        current = self.search_status_label.text()
        if current and not current.startswith("Failed"):
            self.search_status_label.setText(f"{current} | Docker: {extra}")
        else:
            self.search_status_label.setText(f"Docker: {extra}")

    def _run_worker(
        self,
        action: str,
        *,
        engine: str = "",
        stop_other: bool = False,
        preselect: str | None = None,
        base_url: str = "",
    ) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._worker = _EngineWorker(
            action,
            engine=engine,
            stop_other=stop_other,
            base_url=base_url,
        )
        self._worker.finished_signal.connect(self._on_worker_done)
        self._worker.start()

    def _on_worker_done(self, result: dict) -> None:
        worker = self.sender()
        action = worker.action if isinstance(worker, _EngineWorker) else ""
        if action == "status" and result.get("ok"):
            for eng in result.get("engines", []):
                key = eng.get("engine")
                card = self._engine_cards.get(key)
                if not card:
                    continue
                up = bool(eng.get("up"))
                managed = eng.get("managed_pid")
                suffix = ""
                if up and not managed:
                    suffix = " (external)"
                card["status"].setText(f"Status: {'online' if up else 'offline'}{suffix}")
                loaded = ", ".join(eng.get("loaded_models") or []) or "none"
                card["models"].setText(f"Loaded: {loaded}")
                card["toggle"].setText("Stop" if up else "Start")
            settings = load_runtime_settings()
            self._reload_models_for_active_engine(preselect=settings.ollama_model)
            return

        if action == "start":
            if result.get("needs_confirm"):
                ok = QMessageBox.question(
                    self,
                    "Switch engine",
                    result.get("message", "Stop the other engine?"),
                )
                if ok == QMessageBox.StandardButton.Yes and self._pending_start_engine:
                    self._run_worker(
                        "start",
                        engine=self._pending_start_engine,
                        stop_other=True,
                    )
                return
            if result.get("ok") and self._pending_start_engine:
                engine = self._pending_start_engine
                self._pending_start_engine = None
                settings = load_runtime_settings()
                set_engine(settings, engine)
                available = client.discover_aquila_models(
                    primary_base_url=server_control.ENGINES[engine]["base_url"],
                ).get("models") or []
                if not model_available_on_engine(settings.ollama_model, available):
                    pref = prefer_model_for_engine(available, engine)
                    if pref:
                        settings.ollama_model = pref
                else:
                    resolved = resolve_model_tag(settings.ollama_model, available)
                    if resolved:
                        settings.ollama_model = resolved
                save_runtime_settings(settings)
                apply_runtime_settings()
                self._reload_models_for_active_engine(preselect=settings.ollama_model)
                self.settings_applied.emit()
                if self.main_window:
                    self.main_window._update_instance_label()
            self.refresh_engines()
            if result.get("message"):
                self.log_view.appendPlainText(result["message"])
            return

        if action == "models" and result.get("ok"):
            preselect = self._model_preselect or load_runtime_settings().ollama_model
            err = result.get("error")
            base = result.get("base_url") or ""
            self.model_combo.clear()
            models = result.get("models") or []
            if not models:
                hint = err or "No aquila models found"
                if base:
                    hint = f"{hint} (checked {base})"
                self.model_combo.addItem(f"({hint})")
                self.model_status_label.setText(hint)
            else:
                self.model_status_label.setText(
                    f"Found {len(models)} aquila model(s)"
                    + (f" at {base}" if base else "")
                )
                self.model_combo.addItems(models)
                pick = preselect or load_runtime_settings().ollama_model
                resolved = resolve_model_tag(pick, models)
                idx = self.model_combo.findText(resolved or pick)
                if idx < 0 and resolved:
                    idx = self.model_combo.findText(pick)
                if idx >= 0:
                    self.model_combo.setCurrentIndex(idx)
            return

        if action == "logs" and result.get("ok"):
            self.log_view.setPlainText(result.get("text", ""))
            return

        if action in ("stop", "warmup", "eject", "start"):
            self.refresh_engines()
        if result.get("message"):
            self.log_view.appendPlainText(result.get("message", ""))
