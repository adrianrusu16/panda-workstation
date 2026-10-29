// SPDX-License-Identifier: GPL-3.0-or-later
// D4C3-S3: dormant capture source for an independently hosted VM. DO NOT RUN.
// main is unconditionally sealed. No flag, environment or permit opens it.
// A future reviewed launcher must verify the complete VM/runtime/input contract
// before a separately authorized source change may connect this capture body.
#include <KSvg/FrameSvg>
#include <KSvg/ImageSet>
#include <ksvg_version.h>
#include <QBuffer>
#include <QCryptographicHash>
#include <QFile>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QScreen>
#include <cstdio>
#include <stdexcept>

static_assert(QT_VERSION == QT_VERSION_CHECK(6, 12, 0));
static_assert(KSVG_VERSION == QT_VERSION_CHECK(6, 31, 0));

namespace {
void require(bool condition, const char *message)
{
    if (!condition) {
        throw std::runtime_error(message);
    }
}

QByteArray readInput(const QString &path)
{
    QFile file(path);
    require(file.open(QIODevice::ReadOnly) && file.size() <= 65536, "bounded private input required");
    const auto bytes = file.readAll();
    require(bytes.size() == file.size(), "input read incomplete");
    return bytes;
}

QString hash(const QByteArray &bytes)
{
    return QString::fromLatin1(QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex());
}

void writeNew(const QString &name, const QByteArray &bytes)
{
    require(bytes.size() <= 1024 * 1024, "per-output budget exceeded");
    QFile file(QStringLiteral("/out/") + name);
    require(file.open(QIODevice::WriteOnly | QIODevice::NewOnly), "exclusive output creation required");
    require(file.write(bytes) == bytes.size() && file.flush(), "incomplete output");
}

QByteArray rgba(const QImage &source)
{
    require(source.size() == QSize(288, 88), "unexpected native pixel size");
    const auto image = source.convertToFormat(QImage::Format_RGBA8888);
    require(!image.isNull(), "pixel conversion failed");
    QByteArray result;
    for (int y = 0; y < image.height(); ++y) {
        result.append(reinterpret_cast<const char *>(image.constScanLine(y)), image.width() * 4);
    }
    return result;
}

QJsonObject saveImage(const QString &stem, const QImage &image)
{
    const auto pixels = rgba(image); // straight RGBA8888, packed rows, no padding
    QByteArray png;
    QBuffer buffer(&png);
    require(buffer.open(QIODevice::WriteOnly) && image.save(&buffer, "PNG"), "PNG encoding failed");
    writeNew(stem + QStringLiteral(".rgba"), pixels);
    writeNew(stem + QStringLiteral(".png"), png);
    return {{"rgba_sha256", hash(pixels)}, {"png_sha256", hash(png)},
            {"rgba_bytes", pixels.size()}, {"png_bytes", png.size()}};
}

QJsonArray margins(const QMarginsF &value)
{
    return {value.top(), value.right(), value.bottom(), value.left()};
}

[[maybe_unused]] void captureCandidate()
{
    // NOT a launcher or attestation verifier. This body is unreachable in S3.
    // All pre-main containment, input/hash admission, environment, limits and
    // loaded-library provenance remain the future external VM harness's duty.
    require(QString::fromLatin1(qVersion()) == QStringLiteral("6.12.0"), "Qt runtime drift");
    QCoreApplication::setAttribute(Qt::AA_DisableSessionManager);
    QCoreApplication::setLibraryPaths({QStringLiteral("/runtime/plugins")});
    int argc = 1;
    char name[] = "panda-vm-single-frame";
    char *argv[] = {name, nullptr};
    QJsonObject capture;
    {
        QGuiApplication app(argc, argv);
        const auto *screen = QGuiApplication::primaryScreen();
        require(screen && screen->devicePixelRatio() == 1.0, "offscreen screen DPR must be one");
        require(QGuiApplication::platformName() == QStringLiteral("offscreen"), "offscreen QPA required");
        const QString base = QStringLiteral("/inputs/data/plasma/desktoptheme/panda-cyber-s1/");
        const QString asset = base + QStringLiteral("widgets/background.svg");
        const auto before = readInput(asset);
        KSvg::ImageSet images(QStringLiteral("panda-cyber-s1"), QStringLiteral("plasma/desktoptheme"));
        require(images.imageSetName() == QStringLiteral("panda-cyber-s1"), "private image set missing");
        KSvg::FrameSvg frame;
        frame.setImageSet(&images);
        frame.setUsingRenderingCache(false);
        frame.setCacheAllRenderedFrames(false);
        frame.setDevicePixelRatio(1.0);
        frame.setImagePath(asset);
        frame.setElementPrefix(QString());
        frame.setEnabledBorders(KSvg::FrameSvg::AllBorders);
        QJsonArray sections;
        for (const char *prefix : {"", "mask-"}) {
            for (const char *part : {"topleft", "top", "topright", "left", "center", "right",
                                     "bottomleft", "bottom", "bottomright"}) {
                const auto id = QString::fromLatin1(prefix) + QString::fromLatin1(part);
                require(frame.hasElement(id), "native section missing");
                const auto rect = frame.elementRect(id);
                require(rect.isValid(), "invalid native section bounds");
                sections.append(QJsonObject{{"id", id}, {"rect", QJsonArray{
                    rect.x(), rect.y(), rect.width(), rect.height()}}});
            }
        }
        frame.resizeFrame(QSizeF(288, 88));
        require(frame.frameSize() == QSizeF(288, 88), "logical frame size drift");
        const auto pixmap = frame.framePixmap();
        const auto mask = frame.alphaMask();
        require(!pixmap.isNull() && !mask.isNull(), "empty native frame or mask");
        require(pixmap.devicePixelRatio() == 1.0 && mask.devicePixelRatio() == 1.0, "native DPR drift");
        capture = {{"schema_version", 1}, {"candidate_id", "cyber-widget-288x88-dpr1"},
            {"renderer", "KSvg::FrameSvg"}, {"asset_sha256", hash(before)},
            {"qt_compile_version", QT_VERSION_STR}, {"qt_runtime_version", qVersion()},
            {"ksvg_header_version", KSVG_VERSION_STRING},
            {"platform", QGuiApplication::platformName()}, {"screen_dpr", screen->devicePixelRatio()},
            {"logical_size", QJsonArray{288, 88}}, {"pixel_size", QJsonArray{288, 88}},
            {"device_pixel_ratio", pixmap.devicePixelRatio()}, {"mask_device_pixel_ratio", mask.devicePixelRatio()},
            {"margins_trbl", margins(frame.margins())},
            {"fixed_margins_trbl", margins(frame.fixedMargins())},
            {"insets_trbl", QJsonArray{frame.insetSize(KSvg::FrameSvg::TopMargin),
                frame.insetSize(KSvg::FrameSvg::RightMargin), frame.insetSize(KSvg::FrameSvg::BottomMargin),
                frame.insetSize(KSvg::FrameSvg::LeftMargin)}},
            {"sections", sections}, {"frame", saveImage(QStringLiteral("frame"), pixmap.toImage())},
            {"mask", saveImage(QStringLiteral("mask"), mask.toImage())},
            {"native_runtime_verified", false}, {"fallback_status", "unverified"}};
        require(readInput(asset) == before, "input changed during capture");
    } // KSvg/ImageSet/QGuiApplication teardown before writing the capture record.
    // Global destructors still follow; an external exit/teardown receipt is mandatory.
    writeNew(QStringLiteral("capture.json"), QJsonDocument(capture).toJson(QJsonDocument::Indented));
}
} // namespace

int main()
{
    std::fputs("D4C3-S3 source candidate is sealed; execution requires a reviewed source change.\n", stderr);
    return 78;
}
