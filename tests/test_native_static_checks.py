"""Compile/configure-only regressions. Never executes a Qt/KSvg target."""
from pathlib import Path
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
CXX=shutil.which("c++")
CMAKE=shutil.which("cmake")


@unittest.skipUnless(CXX,"existing C++ compiler required for static checks")
class NativeStaticChecks(unittest.TestCase):
    def syntax(self,source,flags=()):
        return subprocess.run([CXX,"-std=c++20","-fsyntax-only","-x","c++",
            "-I"+str(ROOT/"tests/native"),*flags,"-"],input=source,capture_output=True,text=True)

    def test_checked_screen_dpr_accepts_a_nonnull_screen(self):
        source='#include "checked_screen_dpr.h"\nstruct Screen {static constexpr double devicePixelRatio(){return 1.25;}};\nconstexpr Screen screen{};\nstatic_assert(panda::checkedScreenDevicePixelRatio(&screen)==1.25);\n'
        result=self.syntax(source)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_checked_screen_dpr_refuses_null_during_constant_evaluation(self):
        # A static member deliberately permits null->member: only our guard
        # makes this constant expression fail, without running any program.
        source='#include "checked_screen_dpr.h"\nstruct Screen {static constexpr double devicePixelRatio(){return 1.25;}};\nstatic_assert(panda::checkedScreenDevicePixelRatio<Screen>(nullptr)==1.25);\n'
        result=self.syntax(source)
        self.assertNotEqual(result.returncode,0)
        self.assertIn("throw",result.stderr)
        self.assertIn("checkedScreenDevicePixelRatio",result.stderr)

    @unittest.skipUnless(CMAKE,"existing CMake required for target metadata check")
    def test_real_cmake_target_turns_a_warning_into_a_compile_error(self):
        with tempfile.TemporaryDirectory(prefix="panda-s2-cmake-static-") as td:
            base=Path(td);marker=base/"compiler-probe-ran"
            compiler=base/"compiler-must-not-run"
            compiler.write_text("#!"+sys.executable+"\nfrom pathlib import Path\nPath("+repr(str(marker))+").write_text('unexpected')\nraise SystemExit(97)\n")
            compiler.chmod(0o700)
            # Synthetic import targets configure our real CMake target without
            # consulting installed Qt package scripts or running compiler probes.
            for name,target,version in (("Qt6","Qt6::Gui","6.12.0"),("KF6Svg","KF6::Svg","6.31.0")):
                directory=base/name;directory.mkdir()
                (directory/(name+"Config.cmake")).write_text("add_library("+target+" INTERFACE IMPORTED)\nset("+name+"_FOUND TRUE)\n")
                (directory/(name+"ConfigVersion.cmake")).write_text('set(PACKAGE_VERSION "'+version+'")\nset(PACKAGE_VERSION_COMPATIBLE TRUE)\n')
            toolchain=base/"forced-toolchain.cmake"
            toolchain.write_text('set(CMAKE_CXX_COMPILER "'+str(compiler)+'")\n'
                'set(CMAKE_CXX_COMPILER_ID_RUN TRUE)\nset(CMAKE_CXX_COMPILER_ID GNU)\n'
                'set(CMAKE_CXX_COMPILER_VERSION "16.0")\nset(CMAKE_CXX_COMPILER_FORCED TRUE)\n'
                'set(CMAKE_CXX_COMPILER_WORKS TRUE)\nset(CMAKE_CXX_ABI_COMPILED TRUE)\n'
                'set(CMAKE_CXX_STANDARD_COMPUTED_DEFAULT 17)\nset(CMAKE_CXX_EXTENSIONS_COMPUTED_DEFAULT ON)\n')
            env=os.environ.copy()
            for key in ("CXX","CXXFLAGS","CPPFLAGS","LDFLAGS","CMAKE_PREFIX_PATH"):env.pop(key,None)
            result=subprocess.run([CMAKE,"-S",str(ROOT/"tests/native"),"-B",str(base/"build"),
                "-DCMAKE_TOOLCHAIN_FILE="+str(toolchain),"-DQt6_DIR="+str(base/"Qt6"),
                "-DKF6Svg_DIR="+str(base/"KF6Svg"),"-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
                "-DCMAKE_CXX_FLAGS=","-DCMAKE_BUILD_TYPE="],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertFalse(marker.exists(),"configuration executed a compiler probe")
            entries=json.loads((base/"build/compile_commands.json").read_text())
            entry=next(x for x in entries if Path(x["file"])==ROOT/"tests/native/plasma_frame_worker.cpp")
            argv=entry.get("arguments") or shlex.split(entry["command"])
            allowed={"-fPIC","-O2","-Wall","-Wextra","-Wpedantic","-Werror","-std=c++20","-std=gnu++20"}
            flags=[arg for arg in argv if arg in allowed]
            for required in ("-fPIC","-O2","-Wall","-Wextra","-Wpedantic","-Werror"):
                self.assertIn(required,flags)
            warning=self.syntax("int check(){int unused=0;return 0;}\n",flags)
            self.assertNotEqual(warning.returncode,0,"target settings allowed a warning")
            self.assertIn("unused",warning.stderr)
            self.assertIn("error:",warning.stderr)
