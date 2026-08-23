"""First-run setup wizard for packaged Aquila installs."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from agent.core import apply_runtime_settings
from agent.aquila_runtime.hardware_profile import detect_hardware_profile
from agent.aquila_runtime.model_setup import (
    ensure_optional_model_addons,
    ensure_recommended_model,
)
from agent.aquila_runtime.ollama_bundle import ensure_packaged_ollama
from agent.aquila_runtime.paths import get_default_data_root
from agent.aquila_runtime.virtualization import detect_virtualization_status
from agent.remote import server_control
from agent.research import docker_status, start_search
from agent.storage import (
    ensure_agent_data_dirs,
    load_runtime_settings,
    mark_setup_complete,
    save_runtime_settings,
    set_engine,
)


class _OllamaPrepWorker(QThread):
    finished_signal = Signal(bool, str)
    progress = Signal(str)

    def run(self) -> None:
        def on_line(msg: str) -> None:
            self.progress.emit(msg)

        ok, msg = ensure_packaged_ollama(on_progress=on_line)
        if not ok:
            self.finished_signal.emit(False, msg)
            return

        result = server_control.start_engine("stock", stop_other=True)
        if not result.get("ok") and not result.get("needs_confirm"):
            self.finished_signal.emit(
                False, result.get("message", "Failed to start Ollama")
            )
            return

        import time

        for _ in range(60):
            if server_control.probe(server_control.ENGINES["stock"]["base_url"]):
                self.finished_signal.emit(True, "Ollama is running.")
                return
            time.sleep(0.5)

        self.finished_signal.emit(
            False,
            "Ollama started but did not respond on port 11434. Check Settings → Logs.",
        )


class _OptionalModelWorker(QThread):
    finished_signal = Signal(bool, str)
    progress = Signal(str)

    def __init__(
        self,
        profile,
        *,
        include_heretic: bool = False,
        include_full_model: bool = False,
        include_qwopus: bool = False,
        include_stock_aquila: bool = False,
    ):
        super().__init__()
        self.profile = profile
        self.include_heretic = include_heretic
        self.include_full_model = include_full_model
        self.include_qwopus = include_qwopus
        self.include_stock_aquila = include_stock_aquila

    def run(self) -> None:
        def on_line(msg: str) -> None:
            self.progress.emit(msg)

        ok, msg = ensure_optional_model_addons(
            self.profile,
            include_heretic=self.include_heretic,
            include_full_model=self.include_full_model,
            include_qwopus=self.include_qwopus,
            include_stock_aquila=self.include_stock_aquila,
            on_progress=on_line,
        )
        self.finished_signal.emit(ok, msg)


class _ModelWorker(QThread):
    finished_signal = Signal(bool, str)
    progress = Signal(str)

    def __init__(
        self,
        profile,
        *,
        include_heretic: bool = False,
        include_full_model: bool = False,
    ):
        super().__init__()
        self.profile = profile
        self.include_heretic = include_heretic
        self.include_full_model = include_full_model

    def run(self) -> None:
        def on_line(msg: str) -> None:
            self.progress.emit(msg)

        ok, msg = ensure_recommended_model(
            self.profile,
            include_heretic=self.include_heretic,
            include_full_model=self.include_full_model,
            on_progress=on_line,
        )
        self.finished_signal.emit(ok, msg)


class SetupWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aquila Setup")
        self.setWizardStyle(QWizard.ModernStyle)
        self._profile = detect_hardware_profile()
        self._model_worker: _ModelWorker | None = None

        self.addPage(WelcomePage())
        self.addPage(HardwarePage(self._profile))
        self.addPage(OllamaPage())
        self.addPage(ModelPage(self._profile))
        self.addPage(SearchPage())
        self.addPage(DonePage())

    def accept(self) -> None:
        settings = load_runtime_settings()
        settings.ollama_model = self._profile.default_model
        settings.ollama_num_ctx = self._profile.num_ctx
        set_engine(settings, "stock")
        save_runtime_settings(settings)
        apply_runtime_settings()
        mark_setup_complete()
        super().accept()


class WelcomePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Welcome to Aquila")
        self.setSubTitle("Local AI agent — we'll set up Ollama and your model.")
        layout = QVBoxLayout(self)
        self.data_label = QLabel(f"Data folder: {get_default_data_root()}")
        self.data_label.setWordWrap(True)
        layout.addWidget(self.data_label)
        pick = QLabel(
            '<a href="pick">Choose a different data folder…</a>'
        )
        pick.setOpenExternalLinks(False)
        pick.linkActivated.connect(self._pick_folder)
        layout.addWidget(pick)
        layout.addStretch()

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Aquila data folder", str(get_default_data_root())
        )
        if folder:
            import os

            os.environ["AQUILA_DATA_ROOT"] = folder
            ensure_agent_data_dirs()
            self.data_label.setText(f"Data folder: {folder}")


class HardwarePage(QWizardPage):
    def __init__(self, profile):
        super().__init__()
        self.setTitle("Your hardware")
        self.setSubTitle("We picked a preset for your system.")
        layout = QVBoxLayout(self)
        note = profile.performance_note or "Stock Ollama with the aquila model."
        layout.addWidget(QLabel(f"<b>{profile.label}</b><br>{note}"))
        layout.addWidget(
            QLabel(
                f"Default model: <b>{profile.default_model}</b> · "
                f"context: {profile.num_ctx}"
            )
        )
        layout.addStretch()


class OllamaPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Set up Ollama")
        self.setSubTitle("Install the inference engine and start the local server.")
        layout = QVBoxLayout(self)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel("Setting up Ollama automatically when you reach this step…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.retry_btn = QPushButton("Retry")
        self.retry_btn.hide()
        self.retry_btn.clicked.connect(self._retry)
        layout.addWidget(self.retry_btn)
        layout.addStretch()
        self._worker: _OllamaPrepWorker | None = None
        self._started = False
        self._ok = False

    def initializePage(self) -> None:
        if not self._started:
            self._begin()

    def _begin(self) -> None:
        self._started = True
        self._ok = False
        self.retry_btn.hide()
        self.progress.show()
        self.status.setText("Preparing Ollama…")
        self._worker = _OllamaPrepWorker()
        self._worker.progress.connect(self.status.setText)
        self._worker.finished_signal.connect(self._on_done)
        self._worker.start()
        self.completeChanged.emit()

    def _retry(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._started = False
        self.initializePage()

    def _on_done(self, ok: bool, msg: str) -> None:
        self.progress.hide()
        self._ok = ok
        self.status.setText(msg)
        if not ok:
            self.retry_btn.show()
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self._ok


class ModelPage(QWizardPage):
    def __init__(self, profile):
        super().__init__()
        self._profile = profile
        self.setTitle("Download model")
        layout = QVBoxLayout(self)
        if profile.offer_full_model:
            self.setSubTitle(
                f"Installing {profile.default_model} first (~2 GB). "
                "Optimized for CPU — much faster than the full 9B model."
            )
            hint = QLabel(
                "Full Aquila (9B) is optional. Only install it if you need maximum "
                "quality and can wait several minutes per reply on CPU."
            )
            hint.setWordWrap(True)
            layout.addWidget(hint)
            self.full_cb = QCheckBox(
                "Also install full Aquila (qwen3.5:9b, ~7 GB additional download)"
            )
            layout.addWidget(self.full_cb)
            self.heretic_cb = None
        else:
            self.setSubTitle("This may take several minutes on first run.")
            self.full_cb = None
            self.stock_cb = QCheckBox(
                "Also install stock aquila (qwen3.5:9b fallback)"
            )
            layout.addWidget(self.stock_cb)
            self.heretic_cb = QCheckBox(
                "Also install optional aquila_heretic (advanced / less-filtered)"
            )
            layout.addWidget(self.heretic_cb)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.optional_hint = QLabel("")
        self.optional_hint.setWordWrap(True)
        self.optional_hint.hide()
        layout.addWidget(self.optional_hint)
        self.optional_btn = QPushButton("Install selected optional model")
        self.optional_btn.hide()
        self.optional_btn.clicked.connect(self._install_optional)
        layout.addWidget(self.optional_btn)
        self.retry_btn = QPushButton("Retry download")
        self.retry_btn.hide()
        self.retry_btn.clicked.connect(self._retry)
        layout.addWidget(self.retry_btn)
        layout.addStretch()
        self._started = False
        self._model_worker: _ModelWorker | None = None
        self._optional_worker: _OptionalModelWorker | None = None
        self._ok = False
        self._primary_done = False

    def initializePage(self) -> None:
        if not self._started:
            self._begin_primary()

    def _begin_primary(self) -> None:
        self._started = True
        self._ok = False
        self._primary_done = False
        self.retry_btn.hide()
        self.optional_btn.hide()
        self.optional_hint.hide()
        self.progress.show()
        self.status.setText("Downloading primary model…")
        include_full = bool(self.full_cb and self.full_cb.isChecked())
        include_heretic = bool(self.heretic_cb and self.heretic_cb.isChecked())
        self._model_worker = _ModelWorker(
            self._profile,
            include_heretic=include_heretic,
            include_full_model=include_full,
        )
        self._model_worker.progress.connect(self.status.setText)
        self._model_worker.finished_signal.connect(self._on_primary_done)
        self._model_worker.start()
        self.completeChanged.emit()

    def _install_optional(self) -> None:
        if self._optional_worker and self._optional_worker.isRunning():
            return
        include_full = bool(self.full_cb and self.full_cb.isChecked())
        include_heretic = bool(self.heretic_cb and self.heretic_cb.isChecked())
        include_stock = bool(
            getattr(self, "stock_cb", None) and self.stock_cb.isChecked()
        )
        if not include_full and not include_heretic and not include_stock:
            QMessageBox.information(
                self,
                "Optional model",
                "Check an optional model above, then click this button again.",
            )
            return
        self._ok = False
        self.optional_btn.hide()
        self.retry_btn.hide()
        self.progress.show()
        self.status.setText("Installing optional model…")
        self._optional_worker = _OptionalModelWorker(
            self._profile,
            include_heretic=include_heretic,
            include_full_model=include_full,
            include_stock_aquila=include_stock,
        )
        self._optional_worker.progress.connect(self.status.setText)
        self._optional_worker.finished_signal.connect(self._on_optional_done)
        self._optional_worker.start()
        self.completeChanged.emit()

    def _retry(self) -> None:
        if self._model_worker and self._model_worker.isRunning():
            return
        if self._optional_worker and self._optional_worker.isRunning():
            return
        self._started = False
        self.initializePage()

    def _on_primary_done(self, ok: bool, msg: str) -> None:
        self.progress.hide()
        self._ok = ok
        self._primary_done = ok
        if ok:
            self.status.setText(f"✅ {msg}")
            self._show_optional_hint()
        else:
            self.status.setText(msg)
            self.retry_btn.show()
        self.completeChanged.emit()

    def _on_optional_done(self, ok: bool, msg: str) -> None:
        self.progress.hide()
        self._ok = ok
        if ok:
            self.status.setText(f"✅ {msg}")
            self.optional_hint.setText(
                "Optional model installed. Click Next to continue."
            )
            self.optional_hint.show()
            self.optional_btn.hide()
        else:
            self.status.setText(msg)
            self.optional_btn.show()
            self.retry_btn.show()
        self.completeChanged.emit()

    def _show_optional_hint(self) -> None:
        if self.full_cb and not self.full_cb.isChecked():
            self.optional_hint.setText(
                "Primary model is ready. You can check “Also install full Aquila” "
                "above and click Install selected optional model, or click Next to "
                "continue with Aquila Lite only."
            )
            self.optional_hint.show()
            self.optional_btn.show()
        elif self.heretic_cb and (
            not self.heretic_cb.isChecked()
            or (getattr(self, "stock_cb", None) and not self.stock_cb.isChecked())
        ):
            self.optional_hint.setText(
                "Primary model is ready. Check optional stock aquila or heretic above "
                "and click Install selected optional model, or click Next to continue."
            )
            self.optional_hint.show()
            self.optional_btn.show()
        else:
            self.optional_hint.hide()
            self.optional_btn.hide()

    def isComplete(self) -> bool:
        return self._ok


class SearchPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Web search (optional)")
        self.setSubTitle("SearXNG powers research and light web lookup.")
        layout = QVBoxLayout(self)
        virt = detect_virtualization_status()
        try:
            docker = docker_status()
        except Exception as exc:
            docker = {
                "available": False,
                "running": False,
                "message": f"Could not check Docker ({exc})",
            }
        if virt.enabled is False and not docker.get("available"):
            layout.addWidget(
                QLabel(
                    "<b>CPU virtualization appears disabled.</b> Docker Desktop will not "
                    "work until you enable Intel VT-x or AMD-V in BIOS. Aquila chat works "
                    "without web search."
                )
            )
            detail = virt.detail or virt.message
            if detail:
                hint = QLabel(detail)
                hint.setWordWrap(True)
                layout.addWidget(hint)
            layout.addWidget(
                QLabel(
                    "A built-in search option without Docker is planned for Aquila 4.0."
                )
            )
            self.try_docker = None
            layout.addStretch()
            return

        if docker.get("running"):
            layout.addWidget(
                QLabel(
                    "Docker is running. You can start the SearXNG search container now or skip."
                )
            )
            self.try_docker = QCheckBox("Start SearXNG container")
            self.try_docker.setChecked(True)
            layout.addWidget(self.try_docker)
        elif docker.get("available"):
            layout.addWidget(
                QLabel(
                    "Docker is installed on this PC but not running for this user session. "
                    "If Docker Desktop is already open under another Windows account, "
                    "starting it here may fail with Access Denied — skip web search for "
                    "now (chat still works) or start Docker while logged into that account."
                )
            )
            self.try_docker = QCheckBox("Start Docker Desktop and SearXNG container")
            # Default off: multi-user / Access Denied is common and optional.
            self.try_docker.setChecked(False)
            layout.addWidget(self.try_docker)
        else:
            layout.addWidget(
                QLabel(
                    "Docker not detected. Chat works without web search. "
                    "Re-run the Aquila installer to install Docker Desktop, or install "
                    "Docker manually later."
                )
            )
            self.try_docker = None
        layout.addStretch()

    def validatePage(self) -> bool:
        if self.try_docker and self.try_docker.isChecked():
            from agent.aquila_runtime.search_bundle import ensure_search_support_files

            ok, msg = ensure_search_support_files()
            if not ok:
                QMessageBox.warning(self, "Web search", msg)
                return True
            ok, msg = start_search()
            if not ok:
                QMessageBox.warning(
                    self,
                    "Docker",
                    f"{msg}\n\nYou can continue without web search — chat still works.",
                )
        return True


class DonePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Ready")
        self.setSubTitle("Aquila is set up. Open Home to start chatting.")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("You can change models and engines anytime in Settings."))
        layout.addStretch()
