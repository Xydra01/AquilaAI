// apps/aquila_gui/worker/agent_worker.cpp
#include "agent_worker.hpp"

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
        }
        if (rec.interaction) {
            output = QString::fromStdString(rec.interaction->result.llm_facing_output);
        } else if (!rec.note.empty()) {
            output = QString::fromStdString(rec.note);
        }

        emit turnCompleted(static_cast<int>(rec.index), thought, module, action, output);
    };

    try {
        ModuleRegistry registry = ModuleRegistry::builtin();
        ModuleContext ctx;
        ctx.workspace_root = workspace_root_;

        emit statusChanged(QStringLiteral("Running recipe '%1'...").arg(QString::fromStdString(recipe_.recipe_id)));
        AgentLoop loop(*backend_, registry, ctx);
        const auto res = loop.run(recipe_, user_request_, config_);

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

