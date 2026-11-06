// apps/aquila_gui/worker/agent_worker.hpp
#pragma once

#include "aquila/agent/agent_loop.hpp"
#include "aquila/agent/recipes.hpp"
#include "aquila/inference/backend.hpp"
#include "aquila/modules/registry.hpp"

#include <QThread>
#include <QString>

#include <atomic>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <string>

namespace aquila::gui {

class AgentWorker : public QThread {
    Q_OBJECT
public:
    AgentWorker(std::shared_ptr<IInferenceBackend> backend,
                const RecipeCartridge& recipe,
                std::string user_request,
                LoopConfig config,
                std::filesystem::path workspace_root,
                QObject* parent = nullptr);

    void cancel();
    void deliverUserResponse(const QString& text);

signals:
    void tokenStreamed(const QString& token);
    void turnCompleted(int index, const QString& thought, const QString& module,
                       const QString& action, const QString& output);
    void scratchpadUpdated(const QString& active_objective, const QString& checklist_json);
    void statusChanged(const QString& statusText);
    void finished(bool success, const QString& completionOutput);
    void askUserRequested(const QString& question);

protected:
    void run() override;

private:
    std::shared_ptr<IInferenceBackend> backend_;
    RecipeCartridge recipe_;
    std::string user_request_;
    LoopConfig config_;
    std::filesystem::path workspace_root_;

    std::atomic<bool> cancel_flag_{false};
    std::mutex user_reply_mutex_;
    std::condition_variable user_reply_cv_;
    QString user_reply_;
    bool user_reply_ready_ = false;
};

}  // namespace aquila::gui
