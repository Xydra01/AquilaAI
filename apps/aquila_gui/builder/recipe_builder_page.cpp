// apps/aquila_gui/builder/recipe_builder_page.cpp
#include "recipe_builder_page.hpp"
#include "aquila/agent/recipes.hpp"
#include "aquila/modules/registry.hpp"

#include <QDir>
#include <QFile>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QMessageBox>
#include <QVBoxLayout>

namespace aquila::gui {

RecipeBuilderPage::RecipeBuilderPage(QWidget* parent)
    : BasePage(QStringLiteral("Recipe Cartridge Builder"),
               QStringLiteral("Visual Workflow Graph Editor & Lossless Cartridge Authoring"),
               QStringLiteral("🧩"), parent) {
    setupUi();
    populatePalette();
    populateBuiltinCombo();

    // Load initial default cartridge
    loadCartridge(aquila::fn_dev_implement_recipe());
}

RecipeBuilderPage::~RecipeBuilderPage() {
    delete view_;
    view_ = nullptr;
    delete scene_;
    scene_ = nullptr;
    model_.reset();
}

void RecipeBuilderPage::setupUi() {
    auto* layout = contentLayout();

    // Top Toolbar
    auto* topBar = new QHBoxLayout();
    topBar->addWidget(new QLabel(QStringLiteral("Builtin Cartridge:"), this));

    builtinCombo_ = new QComboBox(this);
    builtinCombo_->setMinimumWidth(200);
    topBar->addWidget(builtinCombo_);

    loadButton_ = new QPushButton(QStringLiteral("📥 Load"), this);
    connect(loadButton_, &QPushButton::clicked, this, &RecipeBuilderPage::onLoadBuiltin);
    topBar->addWidget(loadButton_);

    newButton_ = new QPushButton(QStringLiteral("✨ New"), this);
    connect(newButton_, &QPushButton::clicked, this, &RecipeBuilderPage::onNewCartridge);
    topBar->addWidget(newButton_);

    topBar->addSpacing(16);

    autoLayoutButton_ = new QPushButton(QStringLiteral("📐 Auto-Layout"), this);
    connect(autoLayoutButton_, &QPushButton::clicked, this, &RecipeBuilderPage::onAutoLayout);
    topBar->addWidget(autoLayoutButton_);

    validateButton_ = new QPushButton(QStringLiteral("✓ Validate"), this);
    connect(validateButton_, &QPushButton::clicked, this, &RecipeBuilderPage::onValidateCartridge);
    topBar->addWidget(validateButton_);

    saveButton_ = new QPushButton(QStringLiteral("💾 Save to .aquila/"), this);
    saveButton_->setProperty("accent", true);
    connect(saveButton_, &QPushButton::clicked, this, &RecipeBuilderPage::onSaveCartridge);
    topBar->addWidget(saveButton_);

    topBar->addStretch(1);
    layout->addLayout(topBar);

    // Main Splitter: Left Palette | Center Node Graph Canvas | Right JSON Preview
    auto* mainSplitter = new QSplitter(Qt::Horizontal, this);

    // 1. Left Palette
    auto* paletteGroup = new QGroupBox(QStringLiteral("Node Palette"), mainSplitter);
    auto* paletteLayout = new QVBoxLayout(paletteGroup);
    paletteLayout->setContentsMargins(4, 8, 4, 4);

    paletteTree_ = new QTreeWidget(paletteGroup);
    paletteTree_->setHeaderHidden(true);
    connect(paletteTree_, &QTreeWidget::itemDoubleClicked, this, &RecipeBuilderPage::onPaletteItemDoubleClicked);
    paletteLayout->addWidget(paletteTree_);
    mainSplitter->addWidget(paletteGroup);

    // 2. Center Node Graph Canvas
    registry_ = CartridgeGraphBridge::createRegistry();
    model_ = std::make_unique<QtNodes::DataFlowGraphModel>(registry_);
    scene_ = new QtNodes::DataFlowGraphicsScene(*model_, this);
    view_ = new QtNodes::GraphicsView(scene_, mainSplitter);
    mainSplitter->addWidget(view_);

    // 3. Right Live JSON Drawer
    auto* jsonGroup = new QGroupBox(QStringLiteral("Live Cartridge JSON"), mainSplitter);
    auto* jsonLayout = new QVBoxLayout(jsonGroup);
    jsonLayout->setContentsMargins(4, 8, 4, 4);

    jsonPreview_ = new QPlainTextEdit(jsonGroup);
    jsonPreview_->setReadOnly(true);
    jsonPreview_->setFont(QFont(QStringLiteral("Consolas"), 10));
    jsonLayout->addWidget(jsonPreview_);
    mainSplitter->addWidget(jsonGroup);

    mainSplitter->setSizes({180, 680, 340});
    layout->addWidget(mainSplitter, 1);

    // Connect model changes to json update
    connect(model_.get(), &QtNodes::DataFlowGraphModel::nodeCreated, this, &RecipeBuilderPage::updateJsonPreview);
    connect(model_.get(), &QtNodes::DataFlowGraphModel::nodeDeleted, this, &RecipeBuilderPage::updateJsonPreview);
    connect(model_.get(), &QtNodes::DataFlowGraphModel::connectionCreated, this, &RecipeBuilderPage::updateJsonPreview);
    connect(model_.get(), &QtNodes::DataFlowGraphModel::connectionDeleted, this, &RecipeBuilderPage::updateJsonPreview);
}

void RecipeBuilderPage::populatePalette() {
    paletteTree_->clear();

    auto* coreCat = new QTreeWidgetItem(paletteTree_, {QStringLiteral("Core")});
    new QTreeWidgetItem(coreCat, {QStringLiteral("CartridgeRootNode")});
    new QTreeWidgetItem(coreCat, {QStringLiteral("IncludeNode")});
    coreCat->setExpanded(true);

    auto* modCat = new QTreeWidgetItem(paletteTree_, {QStringLiteral("Modules")});
    new QTreeWidgetItem(modCat, {QStringLiteral("ModuleNode")});
    modCat->setExpanded(true);

    auto* hookCat = new QTreeWidgetItem(paletteTree_, {QStringLiteral("Hooks & Gates")});
    new QTreeWidgetItem(hookCat, {QStringLiteral("PreHookNode")});
    new QTreeWidgetItem(hookCat, {QStringLiteral("ValidationHookNode")});
    new QTreeWidgetItem(hookCat, {QStringLiteral("ChecklistNode")});
    hookCat->setExpanded(true);
}

void RecipeBuilderPage::populateBuiltinCombo() {
    builtinCombo_->clear();
    const auto list = aquila::all_builtin_recipes();
    for (const auto& r : list) {
        builtinCombo_->addItem(QString::fromStdString(r.recipe_id));
    }
}

void RecipeBuilderPage::loadCartridge(const RecipeCartridge& cartridge) {
    CartridgeGraphBridge::loadCartridgeIntoModel(cartridge, *model_);
    updateJsonPreview();
    setStatus(QStringLiteral("Loaded cartridge '%1'").arg(QString::fromStdString(cartridge.recipe_id)));
}

RecipeCartridge RecipeBuilderPage::currentCartridge() const {
    return CartridgeGraphBridge::extractCartridgeFromModel(*model_);
}

void RecipeBuilderPage::updateJsonPreview() {
    const RecipeCartridge c = currentCartridge();
    try {
        Json j = c;
        jsonPreview_->setPlainText(QString::fromStdString(j.dump(2)));
    } catch (...) {
        jsonPreview_->setPlainText(QStringLiteral("// Error serializing cartridge to JSON"));
    }
}

void RecipeBuilderPage::onNewCartridge() {
    RecipeCartridge c;
    c.recipe_id = "custom_recipe";
    c.goal_template = "Execute custom objective: {{user_instructions}}";
    loadCartridge(c);
}

void RecipeBuilderPage::onLoadBuiltin() {
    const QString id = builtinCombo_->currentText();
    const auto list = aquila::all_builtin_recipes();
    for (const auto& r : list) {
        if (r.recipe_id == id.toStdString()) {
            loadCartridge(r);
            return;
        }
    }
}

void RecipeBuilderPage::onSaveCartridge() {
    const RecipeCartridge c = currentCartridge();
    if (c.recipe_id.empty()) {
        setStatus(QStringLiteral("Error: Recipe ID cannot be empty."));
        return;
    }

    const QString dirPath = QStringLiteral(".aquila/recipes");
    QDir().mkpath(dirPath);

    const QString filePath = QStringLiteral("%1/%2.recipe.json").arg(dirPath).arg(QString::fromStdString(c.recipe_id));
    QFile file(filePath);
    if (file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        Json j = c;
        file.write(QByteArray::fromStdString(j.dump(2)));
        file.close();
        setStatus(QStringLiteral("Saved cartridge to %1").arg(filePath));
        emit cartridgeSaved(QString::fromStdString(c.recipe_id), QString::fromStdString(j.dump(2)));
    } else {
        setStatus(QStringLiteral("Error writing to %1").arg(filePath));
    }
}

void RecipeBuilderPage::onValidateCartridge() {
    const RecipeCartridge c = currentCartridge();
    const auto reg = ModuleRegistry::builtin();
    try {
        const ModuleContext ctx{std::filesystem::current_path(), 4500};
        reg.validate_recipe(c, ctx);
        setStatus(QStringLiteral("✓ Cartridge '%1' is valid: %2 modules, %3 pre-hooks, %4 checklist items")
            .arg(QString::fromStdString(c.recipe_id))
            .arg(static_cast<qlonglong>(c.load_modules.size()))
            .arg(static_cast<qlonglong>(c.pre_llm_hooks.size()))
            .arg(static_cast<qlonglong>(c.scratchpad_checklist.size())));
    } catch (const std::exception& ex) {
        setStatus(QStringLiteral("✗ Validation failed: %1").arg(QString::fromUtf8(ex.what())));
    }
}

void RecipeBuilderPage::onAutoLayout() {
    const RecipeCartridge c = currentCartridge();
    loadCartridge(c);
    setStatus(QStringLiteral("Auto-layout applied."));
}

void RecipeBuilderPage::onPaletteItemDoubleClicked(QTreeWidgetItem* item, int) {
    if (!item || item->childCount() > 0) return;
    const QString nodeType = item->text(0);

    const QtNodes::NodeId nid = model_->addNode(nodeType);
    model_->setNodeData(nid, QtNodes::NodeRole::Position, QPointF(200.0, 150.0));
    updateJsonPreview();
}

}  // namespace aquila::gui
