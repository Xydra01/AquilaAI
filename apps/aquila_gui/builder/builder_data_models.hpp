// apps/aquila_gui/builder/builder_data_models.hpp
#pragma once

#include "aquila/types/recipe.hpp"

#include <QtNodes/NodeData>
#include <QtNodes/NodeDelegateModel>

#include <QCheckBox>
#include <QComboBox>
#include <QGroupBox>
#include <QLabel>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QVBoxLayout>

namespace aquila::gui {

using QtNodes::NodeData;
using QtNodes::NodeDataType;
using QtNodes::NodeDelegateModel;
using QtNodes::PortIndex;
using QtNodes::PortType;

class FlowData : public NodeData {
public:
    explicit FlowData(QString type = QStringLiteral("FlowData")) : type_(std::move(type)) {}
    NodeDataType type() const override { return {QStringLiteral("FlowData"), type_}; }
private:
    QString type_;
};

// 1. Root Cartridge Node Model
class CartridgeRootNodeModel : public NodeDelegateModel {
    Q_OBJECT
public:
    CartridgeRootNodeModel();
    ~CartridgeRootNodeModel() override = default;

    QString caption() const override { return QStringLiteral("Recipe Cartridge"); }
    QString name() const override { return QStringLiteral("CartridgeRootNode"); }

    unsigned int nPorts(PortType portType) const override;
    NodeDataType dataType(PortType portType, PortIndex portIndex) const override;
    QString portCaption(PortType portType, PortIndex portIndex) const override;
    bool portCaptionVisible(PortType, PortIndex) const override { return true; }

    std::shared_ptr<NodeData> outData(PortIndex) override { return nullptr; }
    void setInData(std::shared_ptr<NodeData>, PortIndex) override {}

    QWidget* embeddedWidget() override { return widget_; }

    QString recipeId() const;
    void setRecipeId(const QString& id);

    QString goalTemplate() const;
    void setGoalTemplate(const QString& goal);

signals:
    void dataChanged();

private:
    QWidget* widget_ = nullptr;
    QLineEdit* idEdit_ = nullptr;
    QPlainTextEdit* goalEdit_ = nullptr;
};

// 2. Module Load Node Model
class ModuleNodeModel : public NodeDelegateModel {
    Q_OBJECT
public:
    ModuleNodeModel();
    ~ModuleNodeModel() override = default;

    QString caption() const override { return QStringLiteral("Module Load"); }
    QString name() const override { return QStringLiteral("ModuleNode"); }

    unsigned int nPorts(PortType portType) const override;
    NodeDataType dataType(PortType portType, PortIndex portIndex) const override;
    QString portCaption(PortType portType, PortIndex portIndex) const override;
    bool portCaptionVisible(PortType, PortIndex) const override { return true; }

    std::shared_ptr<NodeData> outData(PortIndex port) override;
    void setInData(std::shared_ptr<NodeData>, PortIndex) override {}

    QWidget* embeddedWidget() override { return widget_; }

    ModuleLoad toModuleLoad() const;
    void fromModuleLoad(const ModuleLoad& ml);

signals:
    void dataChanged();

private slots:
    void onModuleChanged(const QString& modName);

private:
    QWidget* widget_ = nullptr;
    QComboBox* moduleCombo_ = nullptr;
    QLineEdit* actionsEdit_ = nullptr;
    QPlainTextEdit* initialStateEdit_ = nullptr;
};

// 3. Pre-LLM Hook Node Model
class PreHookNodeModel : public NodeDelegateModel {
    Q_OBJECT
public:
    PreHookNodeModel();
    ~PreHookNodeModel() override = default;

    QString caption() const override { return QStringLiteral("Pre-LLM Hook"); }
    QString name() const override { return QStringLiteral("PreHookNode"); }

    unsigned int nPorts(PortType portType) const override;
    NodeDataType dataType(PortType portType, PortIndex portIndex) const override;
    QString portCaption(PortType portType, PortIndex portIndex) const override;
    bool portCaptionVisible(PortType, PortIndex) const override { return true; }

    std::shared_ptr<NodeData> outData(PortIndex port) override;
    void setInData(std::shared_ptr<NodeData>, PortIndex) override {}

    QWidget* embeddedWidget() override { return widget_; }

    HookCall toHookCall() const;
    void fromHookCall(const HookCall& hk);

signals:
    void dataChanged();

private:
    QWidget* widget_ = nullptr;
    QLineEdit* moduleEdit_ = nullptr;
    QLineEdit* actionEdit_ = nullptr;
    QPlainTextEdit* argsEdit_ = nullptr;
};

// 4. Validation Exit Gate Node Model
class ValidationHookNodeModel : public NodeDelegateModel {
    Q_OBJECT
public:
    ValidationHookNodeModel();
    ~ValidationHookNodeModel() override = default;

    QString caption() const override { return QStringLiteral("Post-LLM Exit Gate"); }
    QString name() const override { return QStringLiteral("ValidationHookNode"); }

    unsigned int nPorts(PortType portType) const override;
    NodeDataType dataType(PortType portType, PortIndex portIndex) const override;
    QString portCaption(PortType portType, PortIndex portIndex) const override;
    bool portCaptionVisible(PortType, PortIndex) const override { return true; }

    std::shared_ptr<NodeData> outData(PortIndex port) override;
    void setInData(std::shared_ptr<NodeData>, PortIndex) override {}

    QWidget* embeddedWidget() override { return widget_; }

    ValidationHook toValidationHook() const;
    void fromValidationHook(const ValidationHook& vh);

signals:
    void dataChanged();

private:
    QWidget* widget_ = nullptr;
    QLineEdit* moduleEdit_ = nullptr;
    QLineEdit* actionEdit_ = nullptr;
    QCheckBox* mustSucceedCheck_ = nullptr;
    QPlainTextEdit* onFailEdit_ = nullptr;
};

// 5. Checklist Node Model
class ChecklistNodeModel : public NodeDelegateModel {
    Q_OBJECT
public:
    ChecklistNodeModel();
    ~ChecklistNodeModel() override = default;

    QString caption() const override { return QStringLiteral("Scratchpad Checklist"); }
    QString name() const override { return QStringLiteral("ChecklistNode"); }

    unsigned int nPorts(PortType portType) const override;
    NodeDataType dataType(PortType portType, PortIndex portIndex) const override;
    QString portCaption(PortType portType, PortIndex portIndex) const override;
    bool portCaptionVisible(PortType, PortIndex) const override { return true; }

    std::shared_ptr<NodeData> outData(PortIndex port) override;
    void setInData(std::shared_ptr<NodeData>, PortIndex) override {}

    QWidget* embeddedWidget() override { return widget_; }

    std::vector<std::string> toChecklist() const;
    void fromChecklist(const std::vector<std::string>& list);

signals:
    void dataChanged();

private:
    QWidget* widget_ = nullptr;
    QPlainTextEdit* listEdit_ = nullptr;
};

// 6. Include Node Model
class IncludeNodeModel : public NodeDelegateModel {
    Q_OBJECT
public:
    IncludeNodeModel();
    ~IncludeNodeModel() override = default;

    QString caption() const override { return QStringLiteral("Include Cartridge"); }
    QString name() const override { return QStringLiteral("IncludeNode"); }

    unsigned int nPorts(PortType portType) const override;
    NodeDataType dataType(PortType portType, PortIndex portIndex) const override;
    QString portCaption(PortType portType, PortIndex portIndex) const override;
    bool portCaptionVisible(PortType, PortIndex) const override { return true; }

    std::shared_ptr<NodeData> outData(PortIndex port) override;
    void setInData(std::shared_ptr<NodeData>, PortIndex) override {}

    QWidget* embeddedWidget() override { return widget_; }

    std::vector<std::string> toIncludes() const;
    void fromIncludes(const std::vector<std::string>& includes);

signals:
    void dataChanged();

private:
    QWidget* widget_ = nullptr;
    QLineEdit* includesEdit_ = nullptr;
};

}  // namespace aquila::gui

