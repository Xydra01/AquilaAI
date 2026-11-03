#include "aquila/core.hpp"

#include <QApplication>
#include <QLabel>
#include <QMainWindow>
#include <QStyle>
#include <QStyleFactory>
#include <QTimer>

#include <cstdio>

int main(int argc, char** argv) {
    QApplication app(argc, argv);
    const bool smoke = app.arguments().contains(QStringLiteral("--smoke"));

    QMainWindow window;
    const auto v = aquila::version();
    window.setWindowTitle(QStringLiteral("Aquila %1").arg(QString::fromUtf8(v.data(), static_cast<qsizetype>(v.size()))));
    window.setCentralWidget(new QLabel(QStringLiteral("Aquila-cpp M0"), &window));
    window.resize(480, 240);
    window.show();

    if (smoke) {
        std::printf("platform=%s\n", qPrintable(QApplication::platformName()));
        std::printf("style=%s\n", qPrintable(QApplication::style()->name()));
        std::printf("styles=%s\n", qPrintable(QStyleFactory::keys().join(QLatin1Char(','))));
        QTimer::singleShot(0, &app, [&app] {
            std::printf("smoke=ok\n");
            std::fflush(stdout);
            app.quit();
        });
    }
    return QApplication::exec();
}
