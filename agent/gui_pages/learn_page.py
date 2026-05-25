"""Learn Mode: Classroom (courses + syllabus) and Archives (NotebookLM-style)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QCheckBox,
    QMessageBox,
    QWidget,
    QSplitter,
    QGroupBox,
    QTreeWidget,
    QTreeWidgetItem,
    QTabWidget,
    QRadioButton,
    QButtonGroup,
    QSpinBox,
    QFileDialog,
)
from PySide6.QtCore import Qt, QThread, Signal

from gui_pages.base import BaseModePage
from gui_theme import mode_accent_style
from gui_widgets.agent_rail import AgentRail
from gui_widgets.execution_log_panel import ExecutionLogPanel
from gui_formatting import format_user_message_html, format_assistant_message_html
from learn_registry import (
    Course,
    Archive,
    create_course,
    create_archive,
    delete_course,
    delete_archive,
    get_course,
    get_archive,
    list_courses,
    list_archives,
    load_syllabus,
    load_tutor_history,
    save_tutor_history,
    load_archive_chat_history,
    save_archive_chat_history,
    load_assessment,
    save_assessment,
    new_assessment_id,
    get_node,
    node_children,
    is_node_unlocked,
    course_sources_dir,
    archive_sources_dir,
    save_course,
    save_archive,
    advance_mastery_on_pass,
    save_syllabus,
)


class _ArchiveIndexWorker(QThread):
    """Background Chroma indexing so the UI stays responsive."""

    finished_signal = Signal(str)

    def __init__(self, instance_id: str, archive_id: str):
        super().__init__()
        self.instance_id = instance_id
        self.archive_id = archive_id

    def run(self) -> None:
        from learn_index import index_archive

        try:
            self.finished_signal.emit(index_archive(self.instance_id, self.archive_id))
        except Exception as exc:
            self.finished_signal.emit(f"❌ Index failed: {exc}")


class LearnPage(BaseModePage):
    MODE = "learn"
    MODE_LABEL = "Learn Mode"

    def __init__(self, main_window):
        super().__init__(main_window)
        self._active_course: Course | None = None
        self._active_archive: Archive | None = None
        self._selected_node_id: str = "root"
        self._tutor_history: list[dict[str, str]] = []
        self._archive_history: list[dict[str, str]] = []
        self._index_worker: _ArchiveIndexWorker | None = None

        root = QVBoxLayout(self)
        header = QLabel("Learn Mode")
        header.setStyleSheet(mode_accent_style("learn"))
        root.addWidget(header)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self._build_home()
        self._build_course_create()
        self._build_classroom()
        self._build_archive_create()
        self._build_archive_workspace()
        self.stack.setCurrentWidget(self.home_widget)

    def on_activate(self) -> None:
        self._refresh_lists()

    # --- Streaming / chat API for main window ---

    def is_streaming_learn_chat(self) -> bool:
        w = self.stack.currentWidget()
        if w is self.classroom_widget and self._active_course:
            return self.class_tabs.currentIndex() == 0
        if w is self.archive_widget and self._active_archive:
            return True
        return False

    def is_course_build_view(self) -> bool:
        return self.stack.currentWidget() is self.course_create_widget

    def is_archive_build_view(self) -> bool:
        return self.stack.currentWidget() is self.archive_create_widget

    def get_chat_input_text(self) -> str:
        if self.is_streaming_learn_chat():
            if self.stack.currentWidget() is self.classroom_widget:
                return self.tutor_rail.chat_input.text().strip()
            return self.archive_rail.chat_input.text().strip()
        return ""

    def clear_chat_input(self) -> None:
        if self.stack.currentWidget() is self.classroom_widget:
            self.tutor_rail.chat_input.clear()
        elif self.stack.currentWidget() is self.archive_widget:
            self.archive_rail.chat_input.clear()

    def append_chat_html(self, html: str) -> None:
        if self.stack.currentWidget() is self.classroom_widget:
            self.tutor_rail.append_chat_html(html)
        elif self.stack.currentWidget() is self.archive_widget:
            self.archive_rail.append_chat_html(html)

    def clear_chat_display(self) -> None:
        if self.stack.currentWidget() is self.classroom_widget:
            self.tutor_rail.clear_chat_display()
        elif self.stack.currentWidget() is self.archive_widget:
            self.archive_rail.clear_chat_display()

    def set_run_buttons_running(self, running: bool) -> None:
        if self.is_streaming_learn_chat():
            if self.stack.currentWidget() is self.classroom_widget:
                self.tutor_rail.set_run_buttons_running(running)
            else:
                self.archive_rail.set_run_buttons_running(running)
        if self.stack.currentWidget() is self.course_create_widget:
            self.course_build_btn.setDisabled(running)
            self.course_back_btn.setDisabled(running)
        if self.stack.currentWidget() is self.archive_create_widget:
            self.archive_create_btn.setDisabled(running)

    def update_ledger(self, text: str, *, clear: bool = False) -> None:
        if self.stack.currentWidget() is self.course_create_widget:
            self.course_log.update_ledger(text, clear=clear)

    def stream_chat_token(self, token: str) -> None:
        if self.stack.currentWidget() is self.classroom_widget:
            self.tutor_rail.stream_chat_token(token)
        else:
            self.archive_rail.stream_chat_token(token)

    def begin_assistant_stream(self) -> None:
        if self.stack.currentWidget() is self.classroom_widget:
            self.tutor_rail.begin_assistant_stream()
        else:
            self.archive_rail.begin_assistant_stream()

    def finalize_streamed_message(self, raw_text: str) -> None:
        from gui_richtext import finalize_streamed_message as fin

        rail = (
            self.tutor_rail
            if self.stack.currentWidget() is self.classroom_widget
            else self.archive_rail
        )
        label = "Tutor" if self.stack.currentWidget() is self.classroom_widget else "Archive"
        fin(
            rail.chat_history,
            raw_text,
            html_formatter=lambda t: format_assistant_message_html(
                f"{label}: {t}"
            ),
        )

    @property
    def attach_button(self):
        if self.is_streaming_learn_chat():
            if self.stack.currentWidget() is self.classroom_widget:
                return self.tutor_rail.attach_button
            return self.archive_rail.attach_button
        if self.stack.currentWidget() is self.course_create_widget:
            return self.course_attach_btn
        if self.stack.currentWidget() is self.archive_create_widget:
            return self.archive_attach_btn
        return None

    def get_learn_chat_history(self) -> list[dict[str, str]]:
        if self.stack.currentWidget() is self.archive_widget:
            return list(self._archive_history)
        return list(self._tutor_history)

    def active_course_id(self) -> str | None:
        return self._active_course.id if self._active_course else None

    def active_archive_id(self) -> str | None:
        return self._active_archive.id if self._active_archive else None

    def active_node_id(self) -> str:
        return self._selected_node_id

    def learn_chat_mode(self) -> str:
        """AgentWorker mode: learn_tutor or learn_archive_chat."""
        if self.stack.currentWidget() is self.archive_widget:
            return "learn_archive_chat"
        return "learn_tutor"

    def persist_learn_turn(self, user_content: str, assistant_content: str) -> None:
        if not assistant_content:
            return
        iid = self.main.active_instance_id
        if self.stack.currentWidget() is self.classroom_widget and self._active_course:
            self._tutor_history.append({"role": "user", "content": user_content})
            self._tutor_history.append({"role": "assistant", "content": assistant_content})
            save_tutor_history(iid, self._active_course.id, self._tutor_history)
        elif self.stack.currentWidget() is self.archive_widget and self._active_archive:
            self._archive_history.append({"role": "user", "content": user_content})
            self._archive_history.append({"role": "assistant", "content": assistant_content})
            save_archive_chat_history(iid, self._active_archive.id, self._archive_history)

    def on_task_finished(self) -> None:
        if self.stack.currentWidget() is self.course_create_widget:
            self._refresh_lists()
            cid = getattr(self.main.worker, "task_name", "").replace(
                "syllabus_build_", "", 1
            )
            iid = self.main.active_instance_id
            from learn_index import index_course_sources

            index_course_sources(iid, cid)
            course = get_course(iid, cid)
            if course and course.build_complete:
                self._open_classroom(course)
            elif course:
                QMessageBox.warning(
                    self,
                    "Syllabus build",
                    "Build finished but course may be incomplete. Check the log.",
                )

    # --- Home ---

    def _build_home(self) -> None:
        self.home_widget = QWidget()
        layout = QVBoxLayout(self.home_widget)
        split = QSplitter(Qt.Horizontal)

        courses_box = QGroupBox("My courses")
        cl = QVBoxLayout(courses_box)
        self.course_list = QListWidget()
        cl.addWidget(self.course_list)
        cr = QHBoxLayout()
        self.open_course_btn = QPushButton("Open classroom")
        self.open_course_btn.clicked.connect(self._open_selected_course)
        self.new_course_btn = QPushButton("New course")
        self.new_course_btn.clicked.connect(self._show_course_create)
        self.del_course_btn = QPushButton("Delete")
        self.del_course_btn.clicked.connect(self._delete_selected_course)
        cr.addWidget(self.open_course_btn)
        cr.addWidget(self.new_course_btn)
        cr.addWidget(self.del_course_btn)
        cl.addLayout(cr)
        split.addWidget(courses_box)

        archives_box = QGroupBox("My archives")
        al = QVBoxLayout(archives_box)
        self.archive_list = QListWidget()
        al.addWidget(self.archive_list)
        ar = QHBoxLayout()
        self.open_archive_btn = QPushButton("Open archive")
        self.open_archive_btn.clicked.connect(self._open_selected_archive)
        self.new_archive_btn = QPushButton("New archive")
        self.new_archive_btn.clicked.connect(self._show_archive_create)
        self.del_archive_btn = QPushButton("Delete")
        self.del_archive_btn.clicked.connect(self._delete_selected_archive)
        ar.addWidget(self.open_archive_btn)
        ar.addWidget(self.new_archive_btn)
        ar.addWidget(self.del_archive_btn)
        al.addLayout(ar)
        split.addWidget(archives_box)

        layout.addWidget(split)
        self.stack.addWidget(self.home_widget)

    def _refresh_lists(self) -> None:
        iid = self.main.active_instance_id
        self.course_list.clear()
        for c in list_courses(iid):
            status = "" if c.build_complete else " [building]"
            item = QListWidgetItem(f"{c.title}{status}")
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            self.course_list.addItem(item)
        self.archive_list.clear()
        for a in list_archives(iid):
            idx = " ✓ indexed" if a.index_ready else ""
            item = QListWidgetItem(f"{a.title} ({a.source_count} sources){idx}")
            item.setData(Qt.ItemDataRole.UserRole, a.id)
            self.archive_list.addItem(item)

    # --- Course create ---

    def _build_course_create(self) -> None:
        self.course_create_widget = QWidget()
        layout = QVBoxLayout(self.course_create_widget)
        top = QHBoxLayout()
        self.course_back_btn = QPushButton("← Back")
        self.course_back_btn.clicked.connect(
            lambda: self.stack.setCurrentWidget(self.home_widget)
        )
        top.addWidget(self.course_back_btn)
        top.addStretch()
        layout.addLayout(top)
        layout.addWidget(QLabel("Course title"))
        self.course_title = QLineEdit()
        layout.addWidget(self.course_title)
        layout.addWidget(QLabel("Topic / focus"))
        self.course_topic = QLineEdit()
        layout.addWidget(self.course_topic)
        layout.addWidget(QLabel("Intake"))
        intake_row = QHBoxLayout()
        self.intake_group = QButtonGroup(self)
        self.intake_files = QRadioButton("Files & notes")
        self.intake_files.setChecked(True)
        self.intake_web = QRadioButton("Topic + web research")
        self.intake_placement = QRadioButton("Placement (short diagnostic)")
        for rb in (self.intake_files, self.intake_web, self.intake_placement):
            self.intake_group.addButton(rb)
            intake_row.addWidget(rb)
        layout.addLayout(intake_row)
        self.course_web_cb = QCheckBox("Enable web research for topic intake")
        layout.addWidget(self.course_web_cb)
        attach_row = QHBoxLayout()
        self.course_attach_btn = QPushButton("📎 Attach course materials")
        self.course_attach_btn.clicked.connect(self.main.open_attachment_dialog)
        attach_row.addWidget(self.course_attach_btn)
        attach_row.addStretch()
        layout.addLayout(attach_row)
        self.course_build_btn = QPushButton("▶️ Build syllabus")
        self.course_build_btn.clicked.connect(self._start_syllabus_build)
        layout.addWidget(self.course_build_btn)
        self.course_log = ExecutionLogPanel(self.main, show_state_tracker=False)
        layout.addWidget(self.course_log, stretch=1)
        self.stack.addWidget(self.course_create_widget)

    def _show_course_create(self) -> None:
        self.course_title.clear()
        self.course_topic.clear()
        self.intake_files.setChecked(True)
        self.course_web_cb.setChecked(False)
        self.course_log.update_ledger("", clear=True)
        self.stack.setCurrentWidget(self.course_create_widget)

    def _intake_type(self) -> str:
        if self.intake_web.isChecked():
            return "topic_web"
        if self.intake_placement.isChecked():
            return "placement"
        return "files"

    def _start_syllabus_build(self) -> None:
        title = self.course_title.text().strip()
        topic = self.course_topic.text().strip() or title
        if not title:
            QMessageBox.warning(self, "Learn", "Enter a course title.")
            return
        iid = self.main.active_instance_id
        intake = self._intake_type()
        course = create_course(iid, title, topic, intake)
        dest = course_sources_dir(iid, course.id)
        dest.mkdir(parents=True, exist_ok=True)
        for src in getattr(self.main, "attached_file_paths", []) or []:
            try:
                shutil.copy2(src, dest / Path(src).name)
            except OSError:
                pass
        web = self.course_web_cb.isChecked() or intake == "topic_web"
        lore = (
            "User enabled web research — use web_search on the search step."
            if web
            else "Do NOT use web_search unless attachments are insufficient."
        )
        placement_note = (
            "Placement intake: synthesize syllabus weighted toward typical weak areas "
            "from user topic (MVP: infer from topic text, no separate quiz UI)."
            if intake == "placement"
            else ""
        )
        prompt = (
            f"Build a learning syllabus for course '{course.title}'.\n"
            f"Topic: {topic}\nIntake: {intake}\ncourse_id={course.id}\n{lore}\n{placement_note}\n"
            f"Steps: ingest → write_syllabus_file (≥8 nodes, ≥5 sub-units in a module/lesson tree) "
            f"→ finalize_course."
        )
        if dest.is_dir() and any(dest.iterdir()):
            from learn_index import index_course_sources

            index_course_sources(iid, course.id)
        task_name = f"syllabus_build_{course.id}"
        from workspace_paths import agent_data_path

        stale = agent_data_path("Agent-Tasks", f"{task_name}.json")
        if stale.is_file():
            try:
                stale.unlink()
            except OSError:
                pass
        self.course_log.update_ledger(f"Building syllabus for '{title}'…\n", clear=True)
        self.main._start_learn_syllabus_build(
            task_name=task_name,
            prompt=prompt,
            chunks=list(self.main.attached_chunks),
            images=list(self.main.attached_images),
            page=self,
            learn_syllabus_web=web,
        )

    # --- Classroom ---

    def _build_classroom(self) -> None:
        self.classroom_widget = QWidget()
        layout = QVBoxLayout(self.classroom_widget)
        top = QHBoxLayout()
        self.class_back_btn = QPushButton("← Courses")
        self.class_back_btn.clicked.connect(self._back_to_home)
        self.class_title = QLabel("Course")
        self.class_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        top.addWidget(self.class_back_btn)
        top.addWidget(self.class_title)
        top.addStretch()
        layout.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        left = QVBoxLayout()
        left_w = QWidget()
        left_w.setLayout(left)
        left.addWidget(QLabel("Syllabus"))
        self.syllabus_tree = QTreeWidget()
        self.syllabus_tree.setHeaderLabels(["Unit", "Tier"])
        self.syllabus_tree.itemClicked.connect(self._on_node_selected)
        left.addWidget(self.syllabus_tree)
        split.addWidget(left_w)

        self.class_tabs = QTabWidget()
        tutor_w = QWidget()
        tl = QVBoxLayout(tutor_w)
        self.tutor_rail = AgentRail(
            self.main,
            placeholder="Ask the tutor — Socratic mode…",
            show_resume=False,
            show_clear=True,
        )
        self.tutor_rail.run_btn.setText("▶️ Ask")
        tl.addWidget(self.tutor_rail)
        self.class_tabs.addTab(tutor_w, "Tutor")

        assess_w = QWidget()
        al = QVBoxLayout(assess_w)
        self.assess_info = QLabel("Select a unit with an assessment.")
        al.addWidget(self.assess_info)
        self.assess_questions = QPlainTextEdit()
        self.assess_questions.setReadOnly(True)
        al.addWidget(self.assess_questions)
        score_row = QHBoxLayout()
        score_row.addWidget(QLabel("Your score %"))
        self.assess_score = QSpinBox()
        self.assess_score.setRange(0, 100)
        self.assess_score.setValue(70)
        score_row.addWidget(self.assess_score)
        al.addLayout(score_row)
        gen_btn = QPushButton("Generate assessment (AI)")
        gen_btn.clicked.connect(self._generate_assessment_ai)
        submit_btn = QPushButton("Submit score")
        submit_btn.clicked.connect(self._submit_assessment)
        btn_row = QHBoxLayout()
        btn_row.addWidget(gen_btn)
        btn_row.addWidget(submit_btn)
        al.addLayout(btn_row)
        self.class_tabs.addTab(assess_w, "Assessment")

        split.addWidget(self.class_tabs)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        layout.addWidget(split)
        self.stack.addWidget(self.classroom_widget)

    def _open_selected_course(self) -> None:
        item = self.course_list.currentItem()
        if not item:
            QMessageBox.information(self, "Learn", "Select a course first.")
            return
        course = get_course(self.main.active_instance_id, item.data(Qt.ItemDataRole.UserRole))
        if not course:
            return
        if not course.build_complete:
            QMessageBox.information(self, "Learn", "Course syllabus is still building.")
            return
        self._open_classroom(course)

    def _open_classroom(self, course: Course) -> None:
        from tool_library.learn_tools import set_learn_runtime

        self._active_course = course
        iid = self.main.active_instance_id
        set_learn_runtime(iid, course_id=course.id)
        self.class_title.setText(course.title)
        self._tutor_history = load_tutor_history(iid, course.id)
        syllabus = load_syllabus(iid, course.id) or {}
        self._selected_node_id = str(syllabus.get("current_node_id", "root"))
        self._populate_syllabus_tree(syllabus)
        self.tutor_rail.clear_chat_display()
        for msg in self._tutor_history:
            role = msg.get("role", "user")
            if role == "user":
                self.tutor_rail.append_chat_html(
                    format_user_message_html("You", msg.get("content", ""))
                )
            else:
                self.tutor_rail.append_chat_html(
                    format_assistant_message_html(msg.get("content", ""))
                )
        self._refresh_assessment_panel()
        self.stack.setCurrentWidget(self.classroom_widget)

    def _populate_syllabus_tree(self, syllabus: dict) -> None:
        self.syllabus_tree.clear()
        root_nodes = node_children(syllabus, None)

        def add_sub(parent_item: QTreeWidgetItem | None, parent_id: str | None) -> None:
            for node in node_children(syllabus, parent_id):
                nid = str(node.get("id", ""))
                tier = int(node.get("mastery_tier", 0))
                unlocked = is_node_unlocked(syllabus, node)
                label = str(node.get("title", nid))
                if not unlocked:
                    label = f"🔒 {label}"
                item = QTreeWidgetItem([label, f"{tier}/5"])
                item.setData(0, Qt.ItemDataRole.UserRole, nid)
                if parent_item:
                    parent_item.addChild(item)
                else:
                    self.syllabus_tree.addTopLevelItem(item)
                add_sub(item, nid)

        if root_nodes:
            add_sub(None, None)
        else:
            for node in syllabus.get("nodes") or []:
                if isinstance(node, dict) and not node.get("parent_id"):
                    tier = int(node.get("mastery_tier", 0))
                    item = QTreeWidgetItem([str(node.get("title")), f"{tier}/5"])
                    item.setData(0, Qt.ItemDataRole.UserRole, node.get("id"))
                    self.syllabus_tree.addTopLevelItem(item)

    def _on_node_selected(self, item: QTreeWidgetItem) -> None:
        nid = item.data(0, Qt.ItemDataRole.UserRole)
        if nid:
            self._selected_node_id = str(nid)
            self._refresh_assessment_panel()

    def _refresh_assessment_panel(self) -> None:
        if not self._active_course:
            return
        iid = self.main.active_instance_id
        syllabus = load_syllabus(iid, self._active_course.id) or {}
        node = get_node(syllabus, self._selected_node_id)
        if not node:
            self.assess_info.setText("No unit selected.")
            return
        aid = node.get("required_assessment_id")
        self.assess_info.setText(
            f"Unit: {node.get('title')} — mastery tier {node.get('mastery_tier', 0)}/5"
        )
        if not aid:
            self.assess_questions.setPlainText(
                "(No assessment yet — click Generate assessment.)"
            )
            return
        spec = load_assessment(iid, self._active_course.id, aid)
        if not spec:
            self.assess_questions.setPlainText("(Assessment file missing.)")
            return
        lines = []
        for i, q in enumerate(spec.get("questions") or [], 1):
            if isinstance(q, dict):
                lines.append(f"{i}. {q.get('prompt', q.get('question', q))}")
            else:
                lines.append(f"{i}. {q}")
        self.assess_questions.setPlainText("\n\n".join(lines))

    def _generate_assessment_ai(self) -> None:
        if not self._active_course:
            return
        iid = self.main.active_instance_id
        syllabus = load_syllabus(iid, self._active_course.id) or {}
        node = get_node(syllabus, self._selected_node_id)
        if not node:
            return
        tier = int(node.get("mastery_tier", 0))
        prompt = (
            f"Generate exactly 5 short quiz questions as a JSON array for unit "
            f"'{node.get('title')}' at mastery tier {tier}. "
            'Each item: {"prompt": "question text"}. JSON only, no markdown.'
        )
        self.main._run_learn_subcall(
            prompt,
            on_done=lambda text: self._save_generated_assessment(text, node, tier),
        )

    def _save_generated_assessment(self, text: str, node: dict, tier: int) -> None:
        if not self._active_course:
            return
        raw = (text or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        try:
            questions = json.loads(raw)
        except json.JSONDecodeError:
            QMessageBox.warning(self, "Assessment", "Could not parse AI response as JSON.")
            return
        from tool_library.learn_tools import generate_assessment, set_learn_runtime

        set_learn_runtime(self.main.active_instance_id, course_id=self._active_course.id)
        msg = generate_assessment(
            str(node.get("id")),
            tier,
            json.dumps(questions),
        )
        QMessageBox.information(self, "Assessment", msg)
        self._refresh_assessment_panel()
        syllabus = load_syllabus(self.main.active_instance_id, self._active_course.id)
        if syllabus:
            self._populate_syllabus_tree(syllabus)

    def _submit_assessment(self) -> None:
        if not self._active_course:
            return
        iid = self.main.active_instance_id
        syllabus = load_syllabus(iid, self._active_course.id) or {}
        node = get_node(syllabus, self._selected_node_id)
        if not node or not node.get("required_assessment_id"):
            QMessageBox.information(self, "Assessment", "Generate an assessment first.")
            return
        from tool_library.learn_tools import record_assessment_result, set_learn_runtime

        set_learn_runtime(iid, course_id=self._active_course.id)
        msg = record_assessment_result(
            self._active_course.id,
            self._selected_node_id,
            str(node["required_assessment_id"]),
            float(self.assess_score.value()),
        )
        QMessageBox.information(self, "Assessment", msg)
        syllabus = load_syllabus(iid, self._active_course.id) or {}
        self._populate_syllabus_tree(syllabus)
        self._refresh_assessment_panel()

    def _back_to_home(self) -> None:
        from tool_library.learn_tools import clear_learn_runtime

        clear_learn_runtime()
        self._active_course = None
        self._tutor_history = []
        self.stack.setCurrentWidget(self.home_widget)
        self._refresh_lists()

    def _delete_selected_course(self) -> None:
        item = self.course_list.currentItem()
        if not item:
            return
        if (
            QMessageBox.question(self, "Delete", "Delete this course and all data?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        delete_course(self.main.active_instance_id, item.data(Qt.ItemDataRole.UserRole))
        self._refresh_lists()

    # --- Archive create / workspace ---

    def _build_archive_create(self) -> None:
        self.archive_create_widget = QWidget()
        layout = QVBoxLayout(self.archive_create_widget)
        top = QHBoxLayout()
        back = QPushButton("← Back")
        back.clicked.connect(lambda: self.stack.setCurrentWidget(self.home_widget))
        top.addWidget(back)
        top.addStretch()
        layout.addLayout(top)
        layout.addWidget(QLabel("Archive title"))
        self.archive_title_edit = QLineEdit()
        layout.addWidget(self.archive_title_edit)
        self.archive_create_btn = QPushButton("Create archive")
        self.archive_create_btn.clicked.connect(self._create_archive_only)
        layout.addWidget(self.archive_create_btn)
        self.stack.addWidget(self.archive_create_widget)

    def _show_archive_create(self) -> None:
        self.archive_title_edit.clear()
        self.stack.setCurrentWidget(self.archive_create_widget)

    def _create_archive_only(self) -> None:
        title = self.archive_title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Learn", "Enter a title.")
            return
        archive = create_archive(self.main.active_instance_id, title)
        self._open_archive(archive)

    def _build_archive_workspace(self) -> None:
        self.archive_widget = QWidget()
        layout = QVBoxLayout(self.archive_widget)
        top = QHBoxLayout()
        self.archive_back_btn = QPushButton("← Archives")
        self.archive_back_btn.clicked.connect(self._archive_back_home)
        self.archive_title_lbl = QLabel("Archive")
        top.addWidget(self.archive_back_btn)
        top.addWidget(self.archive_title_lbl)
        top.addStretch()
        layout.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        side = QVBoxLayout()
        side_w = QWidget()
        side_w.setLayout(side)
        self.source_list = QListWidget()
        side.addWidget(QLabel("Sources"))
        side.addWidget(self.source_list)
        upload_btn = QPushButton("Upload sources…")
        upload_btn.clicked.connect(self._upload_archive_sources)
        reindex_btn = QPushButton("Re-index")
        reindex_btn.clicked.connect(self._reindex_archive)
        side.addWidget(upload_btn)
        side.addWidget(reindex_btn)
        gen_quiz = QPushButton("Generate quiz (AI)")
        gen_quiz.clicked.connect(self._gen_archive_quiz)
        gen_study = QPushButton("Generate study doc (AI)")
        gen_study.clicked.connect(self._gen_archive_study)
        side.addWidget(gen_quiz)
        side.addWidget(gen_study)
        split.addWidget(side_w)

        self.archive_rail = AgentRail(
            self.main,
            placeholder="Chat with your archive (grounded)…",
            show_resume=False,
            show_clear=True,
        )
        self.archive_rail.run_btn.setText("▶️ Send")
        split.addWidget(self.archive_rail)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        layout.addWidget(split)
        self.stack.addWidget(self.archive_widget)

    def _open_selected_archive(self) -> None:
        item = self.archive_list.currentItem()
        if not item:
            QMessageBox.information(self, "Learn", "Select an archive first.")
            return
        archive = get_archive(
            self.main.active_instance_id, item.data(Qt.ItemDataRole.UserRole)
        )
        if archive:
            self._open_archive(archive)

    def _open_archive(self, archive: Archive) -> None:
        from tool_library.learn_tools import set_learn_runtime

        self._active_archive = archive
        iid = self.main.active_instance_id
        set_learn_runtime(iid, archive_id=archive.id)
        self.archive_title_lbl.setText(archive.title)
        self._archive_history = load_archive_chat_history(iid, archive.id)
        self._refresh_source_list()
        self.archive_rail.clear_chat_display()
        for msg in self._archive_history:
            role = msg.get("role", "user")
            if role == "user":
                self.archive_rail.append_chat_html(
                    format_user_message_html("You", msg.get("content", ""))
                )
            else:
                self.archive_rail.append_chat_html(
                    format_assistant_message_html(msg.get("content", ""))
                )
        self.stack.setCurrentWidget(self.archive_widget)
        root = archive_sources_dir(iid, archive.id)
        has_files = root.is_dir() and any(root.iterdir())
        if has_files and (not archive.index_ready or archive.chunk_count == 0):
            self._start_archive_index_worker()

    def _refresh_source_list(self) -> None:
        self.source_list.clear()
        if not self._active_archive:
            return
        root = archive_sources_dir(self.main.active_instance_id, self._active_archive.id)
        if not root.is_dir():
            return
        for p in sorted(root.iterdir()):
            if p.is_file():
                self.source_list.addItem(p.name)

    def _upload_archive_sources(self) -> None:
        if not self._active_archive:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add sources",
            "",
            "Documents (*.pdf *.txt *.md *.docx);;All (*.*)",
        )
        if not paths:
            return
        dest = archive_sources_dir(self.main.active_instance_id, self._active_archive.id)
        dest.mkdir(parents=True, exist_ok=True)
        for p in paths:
            try:
                shutil.copy2(p, dest / Path(p).name)
            except OSError:
                pass
        archive = get_archive(self.main.active_instance_id, self._active_archive.id)
        if archive:
            archive.source_count = len(list(dest.iterdir()))
            save_archive(self.main.active_instance_id, archive)
            self._active_archive = archive
        self._refresh_source_list()
        self._index_active_archive(show_dialog=True)

    def _index_active_archive(self, *, show_dialog: bool = False) -> None:
        if not self._active_archive:
            return
        iid = self.main.active_instance_id
        aid = self._active_archive.id
        from learn_index import index_archive

        msg = index_archive(iid, aid)
        archive = get_archive(iid, aid)
        if archive:
            self._active_archive = archive
            self._refresh_lists()
        if show_dialog or msg.startswith("⚠️") or msg.startswith("❌"):
            QMessageBox.information(self, "Archive index", msg)

    def _start_archive_index_worker(self) -> None:
        if not self._active_archive:
            return
        if self._index_worker and self._index_worker.isRunning():
            return
        iid = self.main.active_instance_id
        aid = self._active_archive.id
        self._index_worker = _ArchiveIndexWorker(iid, aid)
        self._index_worker.finished_signal.connect(self._on_archive_index_done)
        self._index_worker.start()

    def _on_archive_index_done(self, msg: str) -> None:
        if self._active_archive:
            archive = get_archive(self.main.active_instance_id, self._active_archive.id)
            if archive:
                self._active_archive = archive
        self._refresh_lists()
        if msg.startswith("⚠️") or msg.startswith("❌"):
            QMessageBox.warning(self, "Archive index", msg)

    def _reindex_archive(self) -> None:
        if not self._active_archive:
            return
        self._index_active_archive(show_dialog=True)

    def _gen_archive_quiz(self) -> None:
        self._gen_archive_output("quiz")

    def _gen_archive_study(self) -> None:
        self._gen_archive_output("study")

    def _gen_archive_output(self, kind: str) -> None:
        if not self._active_archive:
            return
        from learn_index import search_index, format_retrieval_block

        hits = search_index(
            self.main.active_instance_id,
            "archive",
            self._active_archive.id,
            "key concepts summary",
            top_k=12,
        )
        if not hits:
            QMessageBox.warning(
                self,
                "Learn",
                "No indexed source text found. Upload files, wait for indexing to finish, "
                "or click Re-index. PDFs need extractable text (not scan-only).",
            )
            return
        ctx = format_retrieval_block(hits, "SOURCES")
        label = "quiz with 10 questions" if kind == "quiz" else "study guide outline"
        prompt = (
            f"Write a markdown {label} from these sources only:\n\n{ctx}\n\n"
            "Use clear headings and bullets. No preamble."
        )
        self.main._run_learn_subcall(
            prompt,
            on_done=lambda text: self._save_archive_output(kind, text),
        )

    def _save_archive_output(self, kind: str, text: str) -> None:
        if not self._active_archive:
            return
        from tool_library.learn_tools import (
            generate_archive_quiz,
            generate_archive_study_doc,
            set_learn_runtime,
        )

        set_learn_runtime(
            self.main.active_instance_id, archive_id=self._active_archive.id
        )
        fn = (
            generate_archive_quiz
            if kind == "quiz"
            else generate_archive_study_doc
        )
        msg = fn(self._active_archive.id, text or "")
        QMessageBox.information(self, "Learn", msg)

    def _archive_back_home(self) -> None:
        from tool_library.learn_tools import clear_learn_runtime

        clear_learn_runtime()
        self._active_archive = None
        self._archive_history = []
        self.stack.setCurrentWidget(self.home_widget)
        self._refresh_lists()

    def _delete_selected_archive(self) -> None:
        item = self.archive_list.currentItem()
        if not item:
            return
        if (
            QMessageBox.question(self, "Delete", "Delete this archive?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        delete_archive(self.main.active_instance_id, item.data(Qt.ItemDataRole.UserRole))
        self._refresh_lists()
