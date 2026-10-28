// SPDX-License-Identifier: GPL-3.0-or-later
// Capture-only S2 worker. Do not execute until the external isolation review passes.
#include "checked_screen_dpr.h"
#include <KSvg/FrameSvg>
#include <KSvg/ImageSet>
#include <ksvg_version.h>
#include <QBuffer>
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QGuiApplication>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QScreen>
#include <QStringList>
#include <array>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <cstddef>
#include <dirent.h>
#include <sched.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <sys/syscall.h>
#include <stdexcept>
#include <string>
#include <vector>
#include <fcntl.h>
#include <linux/seccomp.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
constexpr const char *workerPath="/app/panda-frame-worker";
constexpr const char *jobPath="/inputs/job.json";
constexpr const char *attestationPath="/inputs/attestation.json";
struct Asset { const char *path; const char *id; int margin; };
constexpr std::array<Asset,5> assets{{
    {"widgets/background.svg","widget",12},
    {"widgets/translucentbackground.svg","translucent",12},
    {"widgets/panel-background.svg","panel",8},
    {"solid/widgets/panel-background.svg","solid-panel",8},
    {"dialogs/background.svg","dialog",16}}};
constexpr std::array<std::array<int,2>,7> sizes{{{24,24},{288,88},{288,120},{352,168},{1024,48},{352,56},{303,119}}};
constexpr std::array<const char *,9> parts{{"topleft","top","topright","left","center","right","bottomleft","bottom","bottomright"}};
constexpr std::array<const char *,7> namespaces{{"user","mnt","pid","ipc","net","uts","cgroup"}};

void require(bool yes,const char *why) { if(!yes) throw std::runtime_error(why); }

bool hexDigest(const QString &s) {
    if(s.size()!=64)return false;
    for(QChar c:s)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;
    return true;
}
QString digest(const QByteArray &data) {
    return QString::fromLatin1(QCryptographicHash::hash(data,QCryptographicHash::Sha256).toHex());
}
void keys(const QJsonObject &o,std::initializer_list<const char *> expected) {
    std::set<QString> actual,wanted;
    for(auto it=o.begin();it!=o.end();++it)actual.insert(it.key());
    for(auto k:expected)wanted.insert(QString::fromLatin1(k));
    require(actual==wanted,"unexpected JSON fields");
}
bool integer(const QJsonValue &value,int expected) {
    return value.isDouble()&&std::isfinite(value.toDouble())&&value.toDouble()==expected;
}
QByteArray readRegular(const fs::path &path,qsizetype limit) {
    require(path.is_absolute(),"absolute controlled path required");
    fs::path current;
    for(const auto &part:path) {
        current/=part;
        require(!fs::is_symlink(fs::symlink_status(current)),"input symlink refused");
    }
    int fd=::open(path.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);
    require(fd>=0,"controlled input unavailable");
    struct stat before{},after{};
    if(::fstat(fd,&before)!=0 || !S_ISREG(before.st_mode) || before.st_size<0
       || before.st_size>limit || before.st_nlink!=1 || (before.st_mode&0022)!=0
       || (before.st_uid!=0&&before.st_uid!=::geteuid())) {
        ::close(fd);throw std::runtime_error("unsafe input identity/size/mode");
    }
    QByteArray data;char buffer[65536];ssize_t count;
    while((count=::read(fd,buffer,sizeof buffer))!=0) {
        if(count<0) { if(errno==EINTR)continue;::close(fd);throw std::runtime_error("input read failed"); }
        data.append(buffer,count);
        if(data.size()>limit) { ::close(fd);throw std::runtime_error("input grew beyond bound"); }
    }
    const bool unchanged=::fstat(fd,&after)==0&&before.st_dev==after.st_dev&&before.st_ino==after.st_ino
        &&before.st_size==after.st_size&&before.st_mtim.tv_sec==after.st_mtim.tv_sec
        &&before.st_mtim.tv_nsec==after.st_mtim.tv_nsec&&before.st_ctim.tv_sec==after.st_ctim.tv_sec
        &&before.st_ctim.tv_nsec==after.st_ctim.tv_nsec;
    ::close(fd);
    struct stat binding{};
    require(unchanged&&::lstat(path.c_str(),&binding)==0&&binding.st_dev==before.st_dev
            &&binding.st_ino==before.st_ino&&data.size()==before.st_size,"input changed while reading");
    return data;
}
QJsonObject object(const QByteArray &raw) {
    QJsonParseError error{};const auto doc=QJsonDocument::fromJson(raw,&error);
    require(error.error==QJsonParseError::NoError&&doc.isObject(),"object JSON required");
    return doc.object();
}
void privateDirectory(const char *path) {
    struct stat info{};
    require(::lstat(path,&info)==0&&S_ISDIR(info.st_mode)&&info.st_uid==::geteuid()
            &&(info.st_mode&0077)==0,"private owned directory required");
}
void readOnly(const char *path) {
    struct statvfs info{};
    require(::statvfs(path,&info)==0&&(info.f_flag&ST_RDONLY),"read-only runtime/input mount required");
}
std::string procText(const char *path) {
    std::ifstream input(path);require(input.good(),"own process metadata unavailable");
    std::string data((std::istreambuf_iterator<char>(input)),{});
    require(data.size()<1024*1024,"process metadata too large");return data;
}
void verifyMappedFiles(const QJsonObject &manifest) {
    std::istringstream maps(procText("/proc/self/maps"));std::string line;
    std::set<QString> checked;
    while(std::getline(maps,line)) {
        std::istringstream fields(line);std::string address,permissions,offset,device,inode,path;
        require(static_cast<bool>(fields>>address>>permissions>>offset>>device>>inode),"invalid own mapping record");
        if(permissions.find('x')==std::string::npos)continue;
        std::getline(fields>>std::ws,path);
        if(path=="[vdso]"||path=="[vsyscall]")continue;
        require(!path.empty()&&path.front()=='/',"unreviewed anonymous executable mapping");
        const QString file=QString::fromStdString(path);
        require(!file.endsWith(" (deleted)"),"deleted executable mapping");
        if(!checked.insert(file).second)continue;
        const auto hash=manifest.value(file).toString();
        require(hexDigest(hash)&&digest(readRegular(file.toStdString(),64*1024*1024))==hash,
                "executable mapping absent from pinned runtime manifest");
    }
}
void closedDescriptors() {
    struct stat input{},nullDevice{};
    require(::fstat(0,&input)==0&&::stat("/dev/null",&nullDevice)==0
            &&S_ISCHR(input.st_mode)&&input.st_rdev==nullDevice.st_rdev,"stdin must be /dev/null");
    for(int fd:{1,2}) {
        struct stat info{};
        require(::fstat(fd,&info)==0&&S_ISREG(info.st_mode)&&info.st_uid==::geteuid()
                &&info.st_nlink==1&&(info.st_mode&0077)==0,"private regular stdout/stderr required");
    }
    DIR *directory=::opendir("/proc/self/fd");require(directory,"fd inventory unavailable");
    const int own=::dirfd(directory);bool clean=true;
    while(auto *entry=::readdir(directory)) {
        if(entry->d_name[0]=='.')continue;
        char *end=nullptr;const long fd=std::strtol(entry->d_name,&end,10);
        if(!end||*end||fd<0||(fd>2&&fd!=own))clean=false;
    }
    ::closedir(directory);require(clean,"unexpected inherited descriptor");
}
void restrictHelpers() {
#if !defined(__x86_64__)
#error "Review the seccomp architecture policy before building on another architecture"
#endif
    // A second, in-process filter adds no helpers/namespace escape to the
    // mandatory externally installed policy. It does not replace that policy.
    std::vector<sock_filter> rules{
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(seccomp_data,arch)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,AUDIT_ARCH_X86_64,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ERRNO|EPERM),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(seccomp_data,nr)),
        BPF_JUMP(BPF_JMP|BPF_JSET|BPF_K,__X32_SYSCALL_BIT,0,1),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ERRNO|EPERM)};
    for(unsigned call:{__NR_execve,__NR_execveat,__NR_fork,__NR_vfork,__NR_unshare,__NR_setns,
                       __NR_mount,__NR_umount2,__NR_ptrace,__NR_bpf,__NR_userfaultfd,
                       __NR_io_uring_setup,__NR_io_uring_enter,__NR_io_uring_register}) {
        rules.push_back(BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,call,0,1));
        rules.push_back(BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ERRNO|EPERM));
    }
    rules.push_back(BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,__NR_clone3,0,1));
    rules.push_back(BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ERRNO|ENOSYS));
    rules.push_back(BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,__NR_clone,0,3));
    rules.push_back(BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(seccomp_data,args[0])));
    rules.push_back(BPF_JUMP(BPF_JMP|BPF_JSET|BPF_K,CLONE_THREAD,1,0));
    rules.push_back(BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ERRNO|EPERM));
    rules.push_back(BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW));
    sock_fprog program{static_cast<unsigned short>(rules.size()),rules.data()};
    require(::prctl(PR_SET_SECCOMP,SECCOMP_MODE_FILTER,&program)==0,"helper restriction installation failed");
}
QJsonObject guard(const QByteArray &jobBytes) {
    require(::geteuid()!=0,"non-root sandbox identity required");
    require(::prctl(PR_GET_NO_NEW_PRIVS,0,0,0,0)==1,"no-new-privileges required");
    require(::prctl(PR_GET_SECCOMP,0,0,0,0)==SECCOMP_MODE_FILTER,"external syscall filter required");
    require(procText("/proc/self/status").find("CapEff:\t0000000000000000")!=std::string::npos,
            "effective capabilities must be empty");
    readOnly("/");readOnly("/app");readOnly("/inputs");readOnly("/usr/lib");readOnly("/qt-plugins");
    for(const char *path:{"/sys","/run/user","/run/dbus","/dev/dri","/tmp/.X11-unix"})
        require(!fs::exists(path),"host integration path exposed");
    for(const char *path:{"/work/home","/work/config","/work/cache","/work/data","/work/state","/run/private","/out"})
        privateDirectory(path);
    require(fs::is_empty("/out"),"fresh empty output directory required");
    const std::map<std::string,std::string> environment{
        {"HOME","/work/home"},{"XDG_CONFIG_HOME","/work/config"},{"XDG_CACHE_HOME","/work/cache"},
        {"XDG_DATA_HOME","/work/data"},{"XDG_STATE_HOME","/work/state"},{"XDG_RUNTIME_DIR","/run/private"},
        {"XDG_CONFIG_DIRS","/etc/xdg"},{"XDG_DATA_DIRS","/inputs/data"},
        {"QT_QPA_PLATFORM","offscreen"},{"QT_QPA_OFFSCREEN_NO_GLX","1"},{"QT_QPA_PLATFORMTHEME","offscreen"},
        {"QT_PLUGIN_PATH","/qt-plugins"},{"QT_QPA_PLATFORM_PLUGIN_PATH","/qt-plugins/platforms"},
        {"FONTCONFIG_FILE","/inputs/fontconfig/fonts.conf"},{"FONTCONFIG_PATH","/inputs/fontconfig"},
        {"DBUS_SESSION_BUS_ADDRESS","unix:path=/run/panda-denied/session-bus"},
        {"DBUS_SYSTEM_BUS_ADDRESS","unix:path=/run/panda-denied/system-bus"},
        {"LANG","C.UTF-8"},{"LC_ALL","C.UTF-8"},{"TZ","UTC0"},{"PATH","/usr/bin"}};
    for(const auto &[name,value]:environment) {
        const char *actual=std::getenv(name.c_str());
        require(actual&&actual==value,"environment whitelist mismatch");
    }
    for(char **p=::environ;*p;++p) {
        const std::string entry(*p);require(environment.contains(entry.substr(0,entry.find('='))),"unreviewed environment variable");
    }
    closedDescriptors();
    const auto att=object(readRegular(attestationPath,65536));
    keys(att,{"schema_version","job_sha256","worker_sha256","parent_namespaces","linked_files","bundle_sha256","seccomp_sha256"});
    require(integer(att.value("schema_version"),1)&&hexDigest(att.value("bundle_sha256").toString())
            &&hexDigest(att.value("seccomp_sha256").toString()),"attestation manifest identity required");
    require(digest(jobBytes)==att.value("job_sha256").toString(),"job hash not attested");
    char executable[4096];const ssize_t n=::readlink("/proc/self/exe",executable,sizeof executable);
    require(n>0&&std::string(executable,static_cast<size_t>(n))==workerPath,"unexpected executable path");
    require(digest(readRegular(workerPath,16*1024*1024))==att.value("worker_sha256").toString(),"worker binary not attested");
    const auto parents=att.value("parent_namespaces").toObject();
    require(parents.size()==static_cast<int>(namespaces.size()),"all parent namespace identities required");
    for(const char *name:namespaces) {
        bool valid=false;const auto parent=parents.value(name).toString().toULongLong(&valid);
        struct stat current{};const std::string path=std::string("/proc/self/ns/")+name;
        require(valid&&parent!=0&&::stat(path.c_str(),&current)==0&&current.st_ino!=parent,"namespace not isolated");
    }
    for(int family:{AF_UNIX,AF_INET,AF_INET6}) {
        errno=0;int fd=::socket(family,SOCK_STREAM|SOCK_CLOEXEC,0);
        if(fd>=0) { ::close(fd);throw std::runtime_error("socket creation unexpectedly allowed"); }
        require(errno==EPERM,"socket syscall denial not established");
    }
    const auto files=att.value("linked_files").toObject();require(!files.isEmpty(),"runtime file manifest required");
    for(auto it=files.begin();it!=files.end();++it) {
        const QString path=it.key();
        require((path==workerPath||path.startsWith("/usr/lib/")||path.startsWith("/lib/")
                 ||path.startsWith("/lib64/")||path=="/qt-plugins/platforms/libqoffscreen.so")
                &&!path.contains("/../")&&hexDigest(it.value().toString()),"unreviewed runtime file path/hash");
        require(digest(readRegular(path.toStdString(),64*1024*1024))==it.value().toString(),"runtime file hash drift");
    }
    verifyMappedFiles(files);return att;
}
QJsonObject validateJob(const QByteArray &raw) {
    const auto job=object(raw);
    keys(job,{"schema_version","flavor","package_id","scale","radius","palette","asset_sha256","cases","missing_asset"});
    const std::set<QString> flavors{"minimal","cyber","gothic","hybrid","pandawave"};
    const auto flavor=job.value("flavor").toString();
    require(flavors.contains(flavor)&&job.value("package_id").toString()=="panda-"+flavor+"-s1","unsupported package identity");
    require(integer(job.value("schema_version"),1)&&integer(job.value("radius"),12),"unreviewed job schema/radius");
    const auto scale=job.value("scale");const double dpr=scale.toDouble(-1);
    require(scale.isDouble()&&(dpr==1||dpr==1.25||dpr==1.5||dpr==2),"unsupported frame scale");
    const auto palette=job.value("palette").toObject();keys(palette,{"surface","border"});
    for(auto it=palette.begin();it!=palette.end();++it) {
        const auto color=it.value().toString();
        require(color.size()==7&&color[0]=='#',"opaque semantic color required");
        bool ok=false;color.mid(1).toUInt(&ok,16);require(ok,"invalid semantic paint");
    }
    const auto hashes=job.value("asset_sha256").toObject();
    require(hashes.size()==static_cast<int>(assets.size()),"asset hash inventory mismatch");
    const auto cases=job.value("cases").toArray();require(cases.size()==35,"complete 35-case job required");
    int index=0;
    for(const auto &asset:assets) {
        require(hexDigest(hashes.value(asset.path).toString()),"asset hash required");
        for(const auto &size:sizes) {
            const auto item=cases[index++].toObject();keys(item,{"id","asset","size","margin"});
            const auto dim=item.value("size").toArray();
            const QString id=QString::fromLatin1(asset.id)+"-"+QString::number(size[0])+"x"+QString::number(size[1]);
            require(item.value("asset").toString()==asset.path&&item.value("id").toString()==id
                    &&integer(item.value("margin"),asset.margin)&&dim.size()==2
                    &&integer(dim[0],size[0])&&integer(dim[1],size[1]),"unsupported path/id/dimension/margin");
        }
    }
    require(job.value("missing_asset").toString()=="widgets/panda-s2-absent.svg","unreviewed negative probe");
    return job;
}
void writeNew(const QString &name,const QByteArray &bytes) {
    require(!name.contains('/')&&!name.contains(".."),"unsafe output name");
    const auto path=std::string("/out/")+name.toStdString();
    int fd=::open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    require(fd>=0,"output conflict or creation failure");
    qsizetype offset=0;
    while(offset<bytes.size()) {
        const auto n=::write(fd,bytes.constData()+offset,static_cast<size_t>(bytes.size()-offset));
        if(n<0&&errno==EINTR)continue;
        if(n<=0) { ::close(fd);throw std::runtime_error("output write failure"); }
        offset+=n;
    }
    const bool ok=::fsync(fd)==0;::close(fd);require(ok,"output sync failure");
}
QByteArray rgba(const QImage &source) {
    const auto image=source.convertToFormat(QImage::Format_RGBA8888);QByteArray bytes;
    require(!image.isNull()&&image.width()*static_cast<qint64>(image.height())<=4*1024*1024,"frame pixel budget exceeded");
    for(int y=0;y<image.height();++y)bytes.append(reinterpret_cast<const char *>(image.constScanLine(y)),image.width()*4);
    return bytes;
}
void saveImage(const QString &name,const QImage &image) {
    QByteArray png;QBuffer buffer(&png);require(buffer.open(QIODevice::WriteOnly)&&image.save(&buffer,"PNG"),"PNG encoding failed");
    writeNew(name+".png",png);writeNew(name+".rgba",rgba(image));
}
QJsonArray dimensions(const QSizeF &size) { return {size.width(),size.height()}; }
QJsonArray margins(const QMarginsF &value) { return {value.top(),value.right(),value.bottom(),value.left()}; }

QJsonObject capture(const QJsonObject &job) {
    const auto *screen=QGuiApplication::primaryScreen();
    const auto screenDpr=panda::checkedScreenDevicePixelRatio(screen);
    const QString package=job.value("package_id").toString();
    const QString base="/inputs/data/plasma/desktoptheme/"+package+"/";
    const double scale=job.value("scale").toDouble();
    KSvg::ImageSet images(package,"plasma/desktoptheme");
    require(images.imageSetName()==package,"requested private image set unavailable");
    QJsonArray results;
    for(const auto &value:job.value("cases").toArray()) {
        const auto item=value.toObject();const QString asset=item.value("asset").toString();
        const auto original=readRegular((base+asset).toStdString(),65536);
        require(digest(original)==job.value("asset_sha256").toObject().value(asset).toString(),"Panda asset hash drift");
        KSvg::FrameSvg frame;frame.setImageSet(&images);
        frame.setUsingRenderingCache(false);frame.setCacheAllRenderedFrames(false);
        frame.setDevicePixelRatio(scale);frame.setImagePath(base+asset);
        QJsonArray elements;
        for(const char *prefix:{"","mask-"})for(const char *part:parts) {
            const QString id=QString::fromLatin1(prefix)+part;
            require(frame.hasElement(id),"native SVG section missing");
            const auto rect=frame.elementRect(id);
            require(rect.isValid(),"native SVG section has invalid bounds");
            elements.append(QJsonObject{{"id",id},{"rect",QJsonArray{rect.x(),rect.y(),rect.width(),rect.height()}}});
        }
        for(const char *hint:{"hint-top-margin","hint-right-margin","hint-bottom-margin","hint-left-margin","hint-stretch-borders"})
            require(frame.hasElement(hint),"native margin/stretch hint missing");
        frame.setElementPrefix(QString());frame.setEnabledBorders(KSvg::FrameSvg::AllBorders);
        const auto size=item.value("size").toArray();
        frame.resizeFrame(QSizeF(size[0].toInt(),size[1].toInt()));
        require(frame.frameSize()==QSizeF(size[0].toInt(),size[1].toInt()),"native logical frame bounds changed");
        const auto m=frame.margins();const double margin=item.value("margin").toDouble();
        require(m.top()==margin&&m.bottom()==margin&&m.left()==margin&&m.right()==margin,"native margin mismatch");
        const auto pixmap=frame.framePixmap();const auto mask=frame.alphaMask();
        require(!pixmap.isNull()&&!mask.isNull()&&pixmap.devicePixelRatio()==scale,"empty/native DPR mismatch");
        require(mask.size()==pixmap.size()&&mask.devicePixelRatio()==scale,"native mask bounds/DPR differ");
        const auto id=item.value("id").toString();
        saveImage(id,pixmap.toImage());saveImage(id+"-mask",mask.toImage());
        QJsonObject prefixes;
        for(const char *prefix:{"floating","north","south","east","west","shadow"})
            prefixes.insert(prefix,frame.hasElementPrefix(QString::fromLatin1(prefix)));
        results.append(QJsonObject{{"id",id},{"asset",asset},{"availability","supported"},
            {"logical_size",dimensions(frame.frameSize())},{"pixel_size",dimensions(pixmap.size())},
            {"dpr",pixmap.devicePixelRatio()},{"mask_dpr",mask.devicePixelRatio()},
            {"margins",margins(m)},{"fixed_margins",margins(frame.fixedMargins())},
            {"insets",QJsonArray{frame.insetSize(KSvg::FrameSvg::TopMargin),frame.insetSize(KSvg::FrameSvg::RightMargin),
                                frame.insetSize(KSvg::FrameSvg::BottomMargin),frame.insetSize(KSvg::FrameSvg::LeftMargin)}},
            {"prefix_availability",prefixes},{"sections",elements}});
        require(readRegular((base+asset).toStdString(),65536)==original,"input changed during native rendering");
    }
    const QString absent=base+job.value("missing_asset").toString();
    require(!fs::exists(absent.toStdString()),"negative fixture unexpectedly exists");
    KSvg::FrameSvg missing;missing.setImageSet(&images);missing.setUsingRenderingCache(false);
    missing.setImagePath(absent);
    require(!missing.hasElement("center"),"absolute missing path unexpectedly resolved a frame");
    // Do not call framePixmap/alphaMask without a valid center.
    return QJsonObject{{"schema_version",1},{"engine","KSvg::FrameSvg"},{"ksvg_compile_version",KSVG_VERSION_STRING},
        {"qt_compile_version",QT_VERSION_STR},{"qt_runtime_version",qVersion()},
        {"offscreen_screen_dpr",screenDpr},
        {"flavor",job.value("flavor")},{"scale",scale},{"frames",results},
        {"missing_probe",QJsonObject{{"asset",job.value("missing_asset")},{"availability","missing"},{"rendered",false}}},
        {"capture_only",true},{"pixel_acceptance","pending offline analysis"},
        {"native_runtime_verified",false},{"plasma_fallback_status","unverified"}};
}
} // namespace

int main(int argc,char **) {
    try {
        require(argc==1,"no command-line options; fixed controlled inputs only");
        const rlimit noCore{0,0};
        require(::setrlimit(RLIMIT_CORE,&noCore)==0&&::prctl(PR_SET_DUMPABLE,0,0,0,0)==0,"non-dumpable worker required");
        const auto raw=readRegular(jobPath,32768);
        const auto att=guard(raw);
        const auto job=validateJob(raw);
        restrictHelpers();
        QCoreApplication::setAttribute(Qt::AA_DisableSessionManager);
        QCoreApplication::setLibraryPaths(QStringList{"/qt-plugins"});
        QCoreApplication::setOrganizationName("Panda");
        QCoreApplication::setApplicationName("panda-frame-verification");
        QJsonObject result;
        {
            int qtArgc=1;char name[]="panda-frame-verification";char *qtArgv[]={name,nullptr};
            QGuiApplication app(qtArgc,qtArgv);
            require(QGuiApplication::platformName()=="offscreen","unexpected QPA platform");
            verifyMappedFiles(att.value("linked_files").toObject());
            result=capture(job);
            verifyMappedFiles(att.value("linked_files").toObject());
        } // QGuiApplication and scoped KSvg objects are destroyed before the result is written.
        verifyMappedFiles(att.value("linked_files").toObject());
        writeNew("capture.json",QJsonDocument(result).toJson(QJsonDocument::Indented));
        return 0;
    } catch(const std::exception &error) {
        std::fprintf(stderr,"S2 worker refusal: %s\n",error.what());return 1;
    }
}
