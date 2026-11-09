// apps/aquila_gui/worker/agent_worker.cpp
#include "agent_worker.hpp"
#include "aquila/logging/run_logger.hpp"

namespace aquila::gui {

AgentWorker::AgentWorker(std::shared_ptr<IInferenceBackend> backend,
                         const RecipeCartridge& recipe,
                         std::string user_request,
                         LoopConfig config,
                         std::filesystem::path workspace_root,
                         QObject* parent)
    : QThread(parent),
      backend_(std::move(backend)),
      recipe_(recipe),
      user_request_(std::move(user_request)),
      config_(std::move(config)),
      workspace_root_(std::move(workspace_root)) {}

void AgentWorker::cancel() {
    cancel_flag_.store(true);
}

void AgentWorker::deliverUserResponse(const QString& text) {
    {
        std::lock_guard<std::mutex> lock(user_reply_mutex_);
        user_reply_ = text;
        user_reply_ready_ = true;
    }
    user_reply_cv_.notify_one();
}

void AgentWorker::run() {
    if (config_.mode == "chat") {
        emit statusChanged(QStringLiteral("Generating response..."));
        try {
            backend_->rollback_to(0);
            Message sys_msg;
            sys_msg.role = Role::system;
            sys_msg.content = "You are Aquila, an autonomous, highly capable AI assistant and software engineering partner. "
                              "Provide clear, direct, and insightful responses formatted with markdown. "
                              "Do NOT format responses as JSON ActionCall objects unless specifically requested.";
            backend_->append(sys_msg);

            for (const auto& msg : chat_history_) {
                backend_->append(msg);
            }

            Message user_msg;
            user_msg.role = Role::user;
            user_msg.content = user_request_;
            backend_->append(user_msg);

            GenerationParams params;
            params.temperature = 0.6;
            params.constraint = OutputConstraint::none();

            const auto res = backend_->generate(params, [this](std::string_view tok, std::string_view) -> bool {
                emit tokenStreamed(QString::fromUtf8(tok.data(), static_cast<qsizetype>(tok.size())));
                return !cancel_flag_.load();
            });

            if (cancel_flag_.load()) {
                emit statusChanged(QStringLiteral("Generation cancelled by user."));
                emit finished(false, QStringLiteral("Cancelled"));
            } else if (!res.ok) {
                const std::string err = res.error_detail.empty() ? res.error_code : res.error_detail;
                emit statusChanged(QStringLiteral("Error: %1").arg(QString::fromStdString(err)));
                emit finished(false, QString::fromStdString(err));
            } else {
                emit statusChanged(QStringLiteral("Ready"));
                emit finished(true, QString::fromStdString(res.content));
            }
        } catch (const std::exception& e) {
            emit statusChanged(QStringLiteral("Error: %1").arg(e.what()));
            emit finished(false, QString::fromStdString(e.what()));
        }
        return;
    }

    emit statusChanged(QStringLiteral("Initializing agent loop..."));

    config_.on_token = [this](std::string_view tok, std::string_view) -> bool {
        emit tokenStreamed(QString::fromUtf8(tok.data(), static_cast<qsizetype>(tok.size())));
        return !cancel_flag_.load();
    };

    config_.check_cancelled = [this]() -> bool {
        return cancel_flag_.load();
    };

    config_.on_turn = [this](const TurnRecord& rec) {
        QString thought;
        QString module;
        QString action;
        QString output;

        if (rec.call) {
            thought = QString::fromStdString(rec.call->thought);
            module = QString::fromStdString(rec.call->module);
            action = QString::fromStdString(rec.call->action);

            if (rec.call->module == "OrchestratorModule") {
                QString obj = QString::fromStdString(user_request_.empty() ? recipe_.goal_template : user_request_);
                QString hyp;
                QStringList facts;
                QStringList checkList;

                const auto& args = rec.call->args;
                if (args.is_object() && args.contains("notes") && args["notes"].is_object()) {
                    const auto& notes = args["notes"];
                    if (notes.contains("objective") && notes["objective"].is_string()) {
                        obj = QString::fromStdString(notes["objective"].get<std::string>());
                    }
                    if (notes.contains("hypothesis") && notes["hypothesis"].is_string()) {
                        hyp = QString::fromStdString(notes["hypothesis"].get<std::string>());
                    }
                    if (notes.contains("verified_facts") && notes["verified_facts"].is_array()) {
                        for (const auto& f : notes["verified_facts"]) {
                            if (f.is_string()) facts.append(QString::fromStdString(f.get<std::string>()));
                        }
                    }
                    if (notes.contains("checklist") && notes["checklist"].is_array()) {
                        for (const auto& c : notes["checklist"]) {
                            if (c.is_string()) {
                                checkList.append(QString::fromStdString(c.get<std::string>()));
                            } else if (c.is_object() && c.contains("item") && c["item"].is_string()) {
                                const QString state = c.value("done", false) ? QStringLiteral(" [DONE]") : QStringLiteral("");
                                checkList.append(QString::fromStdString(c["item"].get<std::string>()) + state);
                            }
                        }
                    }
                }
                if (checkList.isEmpty()) {
                    for (const auto& item : recipe_.scratchpad_checklist) {
                        checkList.append(QString::fromStdString(item));
                    }
                }
                emit scratchpadUpdated(obj, hyp, facts, checkList);
            }
        }
        bool success = true;
        if (rec.interaction) {
            output = QString::fromStdString(rec.interaction->result.llm_facing_output);
            success = rec.interaction->result.success;
        } else if (!rec.note.empty()) {
            output = QString::fromStdString(rec.note);
            success = rec.parsed;
        }

        emit turnCompleted(static_cast<int>(rec.index), thought, module, action, success, output);
    };

    try {
        ModuleRegistry registry = ModuleRegistry::builtin();
        ModuleContext ctx;
        ctx.workspace_root = workspace_root_;

        QStringList initChecklist;
        for (const auto& item : recipe_.scratchpad_checklist) {
            initChecklist.append(QString::fromStdString(item));
        }
        emit scratchpadUpdated(QString::fromStdString(user_request_.empty() ? recipe_.goal_template : user_request_),
                               QStringLiteral("Formulating execution plan and inspecting context"),
                               {}, initChecklist);

        emit statusChanged(QStringLiteral("Running recipe '%1'...").arg(QString::fromStdString(recipe_.recipe_id)));
        config_.max_repeated_calls = 4;

        auto run_logger = std::make_shared<aquila::logging::RunLogger>();
        run_logger->start_session(recipe_.recipe_id, "gui_task", "gui", user_request_, workspace_root_);
        config_.logger = run_logger;

        AgentLoop loop(*backend_, registry, ctx);
        const auto res = loop.run(recipe_, user_request_, config_);

        if (run_logger && run_logger->is_active()) {
            emit logFileReady(QString::fromStdString(run_logger->log_path().string()),
                              QString::fromStdString(run_logger->jsonl_path().string()));
        }

        if (cancel_flag_.load()) {
            emit statusChanged(QStringLiteral("Task cancelled by user."));
            emit finished(false, QStringLiteral("Task cancelled"));
        } else {
            emit statusChanged(res.success ? QStringLiteral("Task completed successfully.")
                                           : QStringLiteral("Task halted without passing exit gate."));
            emit finished(res.success, QString::fromStdString(res.completion_output));
        }
    } catch (const std::exception& e) {
        emit statusChanged(QStringLiteral("Error: %1").arg(e.what()));
        emit finished(false, QString::fromStdString(e.what()));
    }
}

}  // namespace aquila::gui

