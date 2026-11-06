// apps/aquila_gui/builder/recipe_builder_page.hpp
#pragma once

#include "builder_data_models.hpp"
#include "cartridge_graph_bridge.hpp"
#include "../pages/base_page.hpp"
#include "aquila/types/recipe.hpp"

#include <QtNodes/DataFlowGraphModel>
#include <QtNodes/DataFlowGraphicsScene>
#include <QtNodes/GraphicsView>

#include <QComboBox>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QSplitter>
#include <QTreeWidget>
#include <memory>

namespace aquila::gui {

class RecipeBuilderPage : public BasePage {
    Q_OBJECT
public:
    explicit RecipeBuilderPage(QWidget* parent = nullptr);
    ~RecipeBuilderPage() override;

    void loadCartridge(const RecipeCartridge& cartridge);
    RecipeCartridge currentCartridge() const;

    QtNodes::DataFlowGraphModel* graphModel() const { return model_.get(); }

signals:
    void cartridgeSaved(const QString& recipeId, const QString& jsonContent);

private slots:
    void onNewCartridge();
    void onLoadBuiltin();
    void onSaveCartridge();
    void onValidateCartridge();
    void onAutoLayout();
    void onPaletteItemDoubleClicked(QTreeWidgetItem* item, int column);
    void updateJsonPreview();

private:
    void setupUi();
    void populatePalette();
    void populateBuiltinCombo();

    std::shared_ptr<QtNodes::NodeDelegateModelRegistry> registry_;
    std::unique_ptr<QtNodes::DataFlowGraphModel> model_;
    QtNodes::DataFlowGraphicsScene* scene_ = nullptr;
    QtNodes::GraphicsView* view_ = nullptr;

    QComboBox* builtinCombo_ = nullptr;
    QPushButton* newButton_ = nullptr;
    QPushButton* loadButton_ = nullptr;
    QPushButton* saveButton_ = nullptr;
    QPushButton* validateButton_ = nullptr;
    QPushButton* autoLayoutButton_ = nullptr;

    QTreeWidget* paletteTree_ = nullptr;
    QPlainTextEdit* jsonPreview_ = nullptr;
};

}  // namespace aquila::gui

