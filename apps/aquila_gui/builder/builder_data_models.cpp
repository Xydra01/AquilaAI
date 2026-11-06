// apps/aquila_gui/builder/builder_data_models.cpp
#include "builder_data_models.hpp"

#include <QJsonDocument>
#include <QJsonObject>
#include <sstream>

namespace aquila::gui {

// 1. CartridgeRootNodeModel
CartridgeRootNodeModel::CartridgeRootNodeModel() {
    widget_ = new QWidget();
    auto* layout = new QVBoxLayout(widget_);
    layout->setContentsMargins(4, 4, 4, 4);
    layout->setSpacing(6);

    layout->addWidget(new QLabel(QStringLiteral("Recipe ID:"), widget_));
    idEdit_ = new QLineEdit(QStringLiteral("new_recipe"), widget_);
    layout->addWidget(idEdit_);

    layout->addWidget(new QLabel(QStringLiteral("Goal Template:"), widget_));
    goalEdit_ = new QPlainTextEdit(QStringLiteral("Execute objective: {{user_instructions}}"), widget_);
    goalEdit_->setFixedHeight(60);
    layout->addWidget(goalEdit_);

    connect(idEdit_, &QLineEdit::textChanged, this, &CartridgeRootNodeModel::dataChanged);
    connect(goalEdit_, &QPlainTextEdit::textChanged, this, &CartridgeRootNodeModel::dataChanged);
}

unsigned int CartridgeRootNodeModel::nPorts(PortType portType) const {
    if (portType == PortType::In) return 5;
    return 0;
}

NodeDataType CartridgeRootNodeModel::dataType(PortType portType, PortIndex portIndex) const {
    if (portType == PortType::In) {
        switch (portIndex) {
            case 0: return {QStringLiteral("FlowData"), QStringLiteral("Include")};
            case 1: return {QStringLiteral("FlowData"), QStringLiteral("Module")};
            case 2: return {QStringLiteral("FlowData"), QStringLiteral("PreHook")};
            case 3: return {QStringLiteral("FlowData"), QStringLiteral("Checklist")};
            case 4: return {QStringLiteral("FlowData"), QStringLiteral("ValidationHook")};
            default: break;
        }
    }
    return {QStringLiteral("FlowData"), QStringLiteral("None")};
}

QString CartridgeRootNodeModel::portCaption(PortType portType, PortIndex portIndex) const {
    if (portType == PortType::In) {
        switch (portIndex) {
            case 0: return QStringLiteral("Include");
            case 1: return QStringLiteral("Modules");
            case 2: return QStringLiteral("Pre-Hooks");
            case 3: return QStringLiteral("Checklist");
            case 4: return QStringLiteral("Exit Gate");
            default: break;
        }
    }
    return {};
}

QString CartridgeRootNodeModel::recipeId() const {
    return idEdit_->text().trimmed();
}

void CartridgeRootNodeModel::setRecipeId(const QString& id) {
    idEdit_->setText(id);
}

QString CartridgeRootNodeModel::goalTemplate() const {
    return goalEdit_->toPlainText().trimmed();
}

void CartridgeRootNodeModel::setGoalTemplate(const QString& goal) {
    goalEdit_->setPlainText(goal);
}

// 2. ModuleNodeModel
ModuleNodeModel::ModuleNodeModel() {
    widget_ = new QWidget();
    auto* layout = new QVBoxLayout(widget_);
    layout->setContentsMargins(4, 4, 4, 4);
    layout->setSpacing(4);

    layout->addWidget(new QLabel(QStringLiteral("Module:"), widget_));
    moduleCombo_ = new QComboBox(widget_);
    moduleCombo_->addItems({
        QStringLiteral("WorkspaceModule"),
        QStringLiteral("ExecutionModule"),
        QStringLiteral("KnowledgeModule"),
        QStringLiteral("OrchestratorModule"),
        QStringLiteral("DocumentModule"),
        QStringLiteral("PersonaModule"),
        QStringLiteral("LearnModule"),
        QStringLiteral("ScriptModule")
    });
    layout->addWidget(moduleCombo_);

    layout->addWidget(new QLabel(QStringLiteral("Exposed Actions (csv):"), widget_));
    actionsEdit_ = new QLineEdit(widget_);
    layout->addWidget(actionsEdit_);

    layout->addWidget(new QLabel(QStringLiteral("Initial State (JSON):"), widget_));
    initialStateEdit_ = new QPlainTextEdit(QStringLiteral("{}"), widget_);
    initialStateEdit_->setFixedHeight(50);
    layout->addWidget(initialStateEdit_);

    connect(moduleCombo_, &QComboBox::currentTextChanged, this, &ModuleNodeModel::onModuleChanged);
    connect(actionsEdit_, &QLineEdit::textChanged, this, &ModuleNodeModel::dataChanged);
    connect(initialStateEdit_, &QPlainTextEdit::textChanged, this, &ModuleNodeModel::dataChanged);
}

unsigned int ModuleNodeModel::nPorts(PortType portType) const {
    if (portType == PortType::Out) return 1;
    return 0;
}

NodeDataType ModuleNodeModel::dataType(PortType, PortIndex) const {
    return {QStringLiteral("FlowData"), QStringLiteral("Module")};
}

QString ModuleNodeModel::portCaption(PortType portType, PortIndex) const {
    if (portType == PortType::Out) return QStringLiteral("Module Out");
    return {};
}

std::shared_ptr<NodeData> ModuleNodeModel::outData(PortIndex) {
    return std::make_shared<FlowData>(QStringLiteral("Module"));
}

void ModuleNodeModel::onModuleChanged(const QString&) {
    emit dataChanged();
}

ModuleLoad ModuleNodeModel::toModuleLoad() const {
    ModuleLoad ml;
    ml.module = moduleCombo_->currentText().toStdString();

    const QStringList acts = actionsEdit_->text().split(QLatin1Char(','), Qt::SkipEmptyParts);
    for (const auto& a : acts) {
        const std::string s = a.trimmed().toStdString();
        if (!s.empty()) ml.expose_actions.push_back(s);
    }

    try {
        const std::string raw = initialStateEdit_->toPlainText().toStdString();
        ml.initial_state = raw.empty() ? Json::object() : Json::parse(raw);
    } catch (...) {
        ml.initial_state = Json::object();
    }
    return ml;
}

void ModuleNodeModel::fromModuleLoad(const ModuleLoad& ml) {
    int idx = moduleCombo_->findText(QString::fromStdString(ml.module));
    if (idx >= 0) {
        moduleCombo_->setCurrentIndex(idx);
    } else {
        moduleCombo_->addItem(QString::fromStdString(ml.module));
        moduleCombo_->setCurrentIndex(moduleCombo_->count() - 1);
    }

    QStringList acts;
    for (const auto& a : ml.expose_actions) {
        acts.append(QString::fromStdString(a));
    }
    actionsEdit_->setText(acts.join(QStringLiteral(", ")));

    initialStateEdit_->setPlainText(QString::fromStdString(ml.initial_state.dump(2)));
}

// 3. PreHookNodeModel
PreHookNodeModel::PreHookNodeModel() {
    widget_ = new QWidget();
    auto* layout = new QVBoxLayout(widget_);
    layout->setContentsMargins(4, 4, 4, 4);
    layout->setSpacing(4);

    layout->addWidget(new QLabel(QStringLiteral("Target Module:"), widget_));
    moduleEdit_ = new QLineEdit(widget_);
    layout->addWidget(moduleEdit_);

    layout->addWidget(new QLabel(QStringLiteral("Action:"), widget_));
    actionEdit_ = new QLineEdit(widget_);
    layout->addWidget(actionEdit_);

    layout->addWidget(new QLabel(QStringLiteral("Arguments (JSON):"), widget_));
    argsEdit_ = new QPlainTextEdit(QStringLiteral("{}"), widget_);
    argsEdit_->setFixedHeight(40);
    layout->addWidget(argsEdit_);

    connect(moduleEdit_, &QLineEdit::textChanged, this, &PreHookNodeModel::dataChanged);
    connect(actionEdit_, &QLineEdit::textChanged, this, &PreHookNodeModel::dataChanged);
    connect(argsEdit_, &QPlainTextEdit::textChanged, this, &PreHookNodeModel::dataChanged);
}

unsigned int PreHookNodeModel::nPorts(PortType portType) const {
    if (portType == PortType::Out) return 1;
    return 0;
}

NodeDataType PreHookNodeModel::dataType(PortType, PortIndex) const {
    return {QStringLiteral("FlowData"), QStringLiteral("PreHook")};
}

QString PreHookNodeModel::portCaption(PortType portType, PortIndex) const {
    if (portType == PortType::Out) return QStringLiteral("Hook Out");
    return {};
}

std::shared_ptr<NodeData> PreHookNodeModel::outData(PortIndex) {
    return std::make_shared<FlowData>(QStringLiteral("PreHook"));
}

HookCall PreHookNodeModel::toHookCall() const {
    HookCall hk;
    hk.module = moduleEdit_->text().trimmed().toStdString();
    hk.action = actionEdit_->text().trimmed().toStdString();
    try {
        const std::string raw = argsEdit_->toPlainText().toStdString();
        hk.args = raw.empty() ? Json::object() : Json::parse(raw);
    } catch (...) {
        hk.args = Json::object();
    }
    return hk;
}

void PreHookNodeModel::fromHookCall(const HookCall& hk) {
    moduleEdit_->setText(QString::fromStdString(hk.module));
    actionEdit_->setText(QString::fromStdString(hk.action));
    argsEdit_->setPlainText(QString::fromStdString(hk.args.dump(2)));
}

// 4. ValidationHookNodeModel
ValidationHookNodeModel::ValidationHookNodeModel() {
    widget_ = new QWidget();
    auto* layout = new QVBoxLayout(widget_);
    layout->setContentsMargins(4, 4, 4, 4);
    layout->setSpacing(4);

    layout->addWidget(new QLabel(QStringLiteral("Exit Gate Module:"), widget_));
    moduleEdit_ = new QLineEdit(widget_);
    layout->addWidget(moduleEdit_);

    layout->addWidget(new QLabel(QStringLiteral("Action:"), widget_));
    actionEdit_ = new QLineEdit(widget_);
    layout->addWidget(actionEdit_);

    mustSucceedCheck_ = new QCheckBox(QStringLiteral("Must Succeed"), widget_);
    mustSucceedCheck_->setChecked(true);
    layout->addWidget(mustSucceedCheck_);

    layout->addWidget(new QLabel(QStringLiteral("On-Failure Instruction:"), widget_));
    onFailEdit_ = new QPlainTextEdit(widget_);
    onFailEdit_->setFixedHeight(50);
    layout->addWidget(onFailEdit_);

    connect(moduleEdit_, &QLineEdit::textChanged, this, &ValidationHookNodeModel::dataChanged);
    connect(actionEdit_, &QLineEdit::textChanged, this, &ValidationHookNodeModel::dataChanged);
    connect(mustSucceedCheck_, &QCheckBox::toggled, this, &ValidationHookNodeModel::dataChanged);
    connect(onFailEdit_, &QPlainTextEdit::textChanged, this, &ValidationHookNodeModel::dataChanged);
}

unsigned int ValidationHookNodeModel::nPorts(PortType portType) const {
    if (portType == PortType::Out) return 1;
    return 0;
}

NodeDataType ValidationHookNodeModel::dataType(PortType, PortIndex) const {
    return {QStringLiteral("FlowData"), QStringLiteral("ValidationHook")};
}

QString ValidationHookNodeModel::portCaption(PortType portType, PortIndex) const {
    if (portType == PortType::Out) return QStringLiteral("Gate Out");
    return {};
}

std::shared_ptr<NodeData> ValidationHookNodeModel::outData(PortIndex) {
    return std::make_shared<FlowData>(QStringLiteral("ValidationHook"));
}

ValidationHook ValidationHookNodeModel::toValidationHook() const {
    ValidationHook vh;
    vh.module = moduleEdit_->text().trimmed().toStdString();
    vh.action = actionEdit_->text().trimmed().toStdString();
    vh.must_succeed = mustSucceedCheck_->isChecked();
    vh.on_failure_instruction = onFailEdit_->toPlainText().trimmed().toStdString();
    return vh;
}

void ValidationHookNodeModel::fromValidationHook(const ValidationHook& vh) {
    moduleEdit_->setText(QString::fromStdString(vh.module));
    actionEdit_->setText(QString::fromStdString(vh.action));
    mustSucceedCheck_->setChecked(vh.must_succeed);
    onFailEdit_->setPlainText(QString::fromStdString(vh.on_failure_instruction));
}

// 5. ChecklistNodeModel
ChecklistNodeModel::ChecklistNodeModel() {
    widget_ = new QWidget();
    auto* layout = new QVBoxLayout(widget_);
    layout->setContentsMargins(4, 4, 4, 4);
    layout->setSpacing(4);

    layout->addWidget(new QLabel(QStringLiteral("Checklist Items (one per line):"), widget_));
    listEdit_ = new QPlainTextEdit(widget_);
    listEdit_->setFixedHeight(80);
    layout->addWidget(listEdit_);

    connect(listEdit_, &QPlainTextEdit::textChanged, this, &ChecklistNodeModel::dataChanged);
}

unsigned int ChecklistNodeModel::nPorts(PortType portType) const {
    if (portType == PortType::Out) return 1;
    return 0;
}

NodeDataType ChecklistNodeModel::dataType(PortType, PortIndex) const {
    return {QStringLiteral("FlowData"), QStringLiteral("Checklist")};
}

QString ChecklistNodeModel::portCaption(PortType portType, PortIndex) const {
    if (portType == PortType::Out) return QStringLiteral("Checklist Out");
    return {};
}

std::shared_ptr<NodeData> ChecklistNodeModel::outData(PortIndex) {
    return std::make_shared<FlowData>(QStringLiteral("Checklist"));
}

std::vector<std::string> ChecklistNodeModel::toChecklist() const {
    std::vector<std::string> items;
    const QStringList lines = listEdit_->toPlainText().split(QLatin1Char('\n'), Qt::SkipEmptyParts);
    for (const auto& line : lines) {
        const std::string s = line.trimmed().toStdString();
        if (!s.empty()) items.push_back(s);
    }
    return items;
}

void ChecklistNodeModel::fromChecklist(const std::vector<std::string>& list) {
    QStringList lines;
    for (const auto& item : list) {
        lines.append(QString::fromStdString(item));
    }
    listEdit_->setPlainText(lines.join(QStringLiteral("\n")));
}

// 6. IncludeNodeModel
IncludeNodeModel::IncludeNodeModel() {
    widget_ = new QWidget();
    auto* layout = new QVBoxLayout(widget_);
    layout->setContentsMargins(4, 4, 4, 4);
    layout->setSpacing(4);

    layout->addWidget(new QLabel(QStringLiteral("Included Recipes (csv):"), widget_));
    includesEdit_ = new QLineEdit(widget_);
    layout->addWidget(includesEdit_);

    connect(includesEdit_, &QLineEdit::textChanged, this, &IncludeNodeModel::dataChanged);
}

unsigned int IncludeNodeModel::nPorts(PortType portType) const {
    if (portType == PortType::Out) return 1;
    return 0;
}

NodeDataType IncludeNodeModel::dataType(PortType, PortIndex) const {
    return {QStringLiteral("FlowData"), QStringLiteral("Include")};
}

QString IncludeNodeModel::portCaption(PortType portType, PortIndex) const {
    if (portType == PortType::Out) return QStringLiteral("Include Out");
    return {};
}

std::shared_ptr<NodeData> IncludeNodeModel::outData(PortIndex) {
    return std::make_shared<FlowData>(QStringLiteral("Include"));
}

std::vector<std::string> IncludeNodeModel::toIncludes() const {
    std::vector<std::string> items;
    const QStringList parts = includesEdit_->text().split(QLatin1Char(','), Qt::SkipEmptyParts);
    for (const auto& p : parts) {
        const std::string s = p.trimmed().toStdString();
        if (!s.empty()) items.push_back(s);
    }
    return items;
}

void IncludeNodeModel::fromIncludes(const std::vector<std::string>& includes) {
    QStringList parts;
    for (const auto& inc : includes) {
        parts.append(QString::fromStdString(inc));
    }
    includesEdit_->setText(parts.join(QStringLiteral(", ")));
}

}  // namespace aquila::gui

